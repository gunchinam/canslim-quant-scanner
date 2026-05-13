# -*- coding: utf-8 -*-
"""realtime_screener.py - 실시간 종목 스크리너 (alphaswarm 패턴 기반).

한국 주식 시장에서 자연어 전략 규칙을 기반으로 매수 후보를 스크리닝합니다.

파이프라인:
    1단계 (결정적): 거래대금 상위 50종목 추출 (KIS API, KOSPI+KOSDAQ 병합)
    2단계 (결정적): 외인/기관/프로그램 모두 순매수인 종목 필터 (KIS API)
    3단계 (LLM):    30분봉 + 5분봉 패턴 자율 분석 (Claude)

사용법:
    python realtime_screener.py                         # 기본 전략
    python realtime_screener.py --strategy "커스텀 전략"  # 커스텀
    python realtime_screener.py --dry-run               # LLM 없이 수급 필터까지만
    python realtime_screener.py --top 50                # 상위 50종목 기준
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List, Optional

# kis_api 임포트 (같은 디렉토리)
try:
    from kis_api import get_volume_rank, get_investor_trend, get_minute_candles, is_available
except ImportError:
    print("[ERROR] kis_api.py를 찾을 수 없습니다. 같은 디렉토리에 있어야 합니다.")
    sys.exit(1)


# ── 기본 전략 프롬프트 ─────────────────────────────────────────────────────────
DEFAULT_STRATEGY_RULES = """
당신은 한국 주식 시장의 단기 매매 전문가입니다.
아래 분봉 데이터를 분석하여 매수 적합성을 판단하세요.

[30분봉 판단 기준 - 자율 판단]
- 추세 방향성이 있는가 (눕지 않은 봉, 기울기가 있는 캔들)
- 장대음봉이 없는가 (음봉이라도 꼬리가 길면 긍정적)
- 캔들 패턴이 긍정적인가 (양봉 연속, 아랫꼬리 반등, 상승 추세 등)
- 거래량이 증가 추세인가

[5분봉 판단 기준 - 자율 판단]
- 반전 신호가 보이는가 (하락 후 반등 캔들, 망치형, 역망치형)
- 또는 상승 추세 지속 패턴인가 (연속 양봉, 고점 갱신)
- 거래량이 동반되는가 (가격 상승 시 거래량 증가)
- 음봉 연속이나 장대음봉이 아닌가

위 기준을 종합하여 다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{
  "recommendation": "BUY" | "WATCH" | "SKIP",
  "confidence": 0.0~1.0,
  "reason_30m": "30분봉 판단 근거 (1~2문장)",
  "reason_5m": "5분봉 판단 근거 (1~2문장)"
}

BUY: 명확한 매수 신호, WATCH: 지켜볼 필요, SKIP: 패스
""".strip()


# ── CandleStrategy (alphaswarm Strategy 패턴) ─────────────────────────────────
class CandleStrategy:
    """분봉 분석 전략. alphaswarm의 Strategy 클래스 패턴 차용."""

    def __init__(
        self,
        rules: str = DEFAULT_STRATEGY_RULES,
        model_id: str = "claude-sonnet-4-6",
    ):
        self.rules = rules
        self.model_id = model_id


# ── 포맷 헬퍼 ─────────────────────────────────────────────────────────────────
def _format_candles(candles: List[Dict[str, Any]], label: str) -> str:
    """분봉 데이터를 LLM이 읽기 좋은 텍스트로 변환."""
    if not candles:
        return f"[{label}] 데이터 없음"

    lines = [f"[{label}] (시간 | 시가 | 고가 | 저가 | 종가 | 거래량)"]
    for c in candles:
        t = str(c.get("time", "")).zfill(6)
        time_str = f"{t[:2]}:{t[2:4]}"
        lines.append(
            f"  {time_str} | {c.get('open', 0):>8,} | {c.get('high', 0):>8,} | "
            f"{c.get('low', 0):>8,} | {c.get('close', 0):>8,} | {c.get('volume', 0):>10,}"
        )
    return "\n".join(lines)


# ── LLM 분석 ──────────────────────────────────────────────────────────────────
def _call_llm(prompt: str, model_id: str) -> Optional[Dict[str, Any]]:
    """anthropic API로 LLM 호출 후 JSON 파싱.

    Returns None on any failure (caller handles gracefully).
    """
    try:
        import anthropic
    except ImportError:
        print("[ERROR] anthropic 패키지가 없습니다: pip install anthropic")
        return None

    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=model_id,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()

        # JSON 코드블록 추출
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        return json.loads(text)
    except Exception:
        return None


# ── 메인 스크리너 ─────────────────────────────────────────────────────────────
class RealtimeScreener:
    """alphaswarm의 AnalyzeTradingStrategy 패턴을 한국 주식에 적용한 실시간 스크리너."""

    def __init__(self, strategy: CandleStrategy):
        self.strategy = strategy

    def run(self, top_n: int = 50, dry_run: bool = False) -> List[Dict[str, Any]]:
        """3단계 필터링 파이프라인 실행.

        Returns:
            BUY 또는 WATCH로 분류된 종목 리스트 (dry_run 시 수급 통과 종목 전체).
        """
        print(f"\n{'='*60}")
        print("  실시간 종목 스크리너")
        print(f"{'='*60}")

        # ── 1단계: 거래대금 상위 종목 (ETF/선물 제외) ────────────────────────
        # KIS volume-rank는 KOSPI/KOSDAQ 각 최대 30종목(합 60). ETF 필터링으로 빠지는 종목을
        # 감안해 raw를 충분히 받아온 뒤 일반 주식만 추려 정확히 top_n개로 자른다.
        raw_fetch = max(top_n * 2, 60)
        print(f"\n[1단계] 거래대금 상위 {top_n}종목 조회 중 (KOSPI+KOSDAQ raw {raw_fetch}, ETF/선물 제외)...")
        raw_universe = get_volume_rank(raw_fetch)
        if not raw_universe:
            print("  [!] 거래대금 순위 조회 실패. KIS API 키 및 네트워크를 확인하세요.")
            return []

        # ETF·인버스·레버리지·선물 제외 (운용사 이름 키워드 필터)
        _ETF_KEYWORDS = (
            "KODEX", "TIGER", "KINDEX", "ARIRANG", "KOSEF", "KBSTAR",
            "HANARO", "ACE ", "SOL ", "RISE", "TIMEFOLIO", "PLUS",
            "WON ", "BNK", "MAHANARO", "SMART", "FOCUS",
            "인버스", "레버리지", "선물", "ETF",
        )
        filtered = [
            s for s in raw_universe
            if not any(kw in s.get("name", "").upper() for kw in _ETF_KEYWORDS)
        ]
        universe = filtered[:top_n]
        print(f"  → raw {len(raw_universe)} → 일반주식 {len(filtered)} → 유니버스 {len(universe)}종목")

        # ── 2단계: 수급 필터 (외인+기관 모두 순매수) ─────────────────────────
        print(f"\n[2단계] 수급 필터 (외인+기관 순매수) 적용 중...")
        supply_filtered: List[Dict[str, Any]] = []

        for i, stock in enumerate(universe):
            code = stock["code"]
            trend = get_investor_trend(code)

            f    = trend.get("foreign", 0)
            inst = trend.get("institution", 0)

            if f > 0 and inst > 0:
                stock["trend"] = trend
                supply_filtered.append(stock)
                print(
                    f"  [OK] {stock['name']}({code}) - "
                    f"외인:{f:+,} 기관:{inst:+,}"
                )

            # rate limiting: 10종목마다 잠시 대기
            if (i + 1) % 10 == 0:
                time.sleep(0.1)

        print(f"\n  → 수급 통과: {len(supply_filtered)} / {len(universe)}종목 (외인+기관 순매수)")

        if not supply_filtered:
            print("  [!] 수급 조건을 만족하는 종목이 없습니다.")
            return []

        if dry_run:
            print("\n[dry-run] LLM 분석 생략. 수급 필터 결과만 반환합니다.")
            return supply_filtered

        # ── 3단계: LLM 분봉 분석 ──────────────────────────────────────────────
        print(f"\n[3단계] LLM 분봉 분석 중 (모델: {self.strategy.model_id})...")
        results: List[Dict[str, Any]] = []

        for stock in supply_filtered:
            code = stock["code"]
            name = stock["name"]
            print(f"\n  [{name} / {code}] 분봉 수집 중...", end=" ", flush=True)

            candles_30m = get_minute_candles(code, period=30, count=20)
            candles_5m  = get_minute_candles(code, period=5,  count=20)
            print(f"30분봉:{len(candles_30m)}개 / 5분봉:{len(candles_5m)}개")

            analysis = self.analyze_candles(stock, candles_30m, candles_5m)
            rec = analysis.get("recommendation", "SKIP")

            if rec in ("BUY", "WATCH"):
                results.append({**stock, "analysis": analysis})
                marker = "[BUY]  " if rec == "BUY" else "[WATCH]"
                conf   = analysis.get("confidence", 0.0)
                print(f"  {marker} (신뢰도: {conf:.0%})")
                print(f"    30분봉: {analysis.get('reason_30m', '')}")
                print(f"    5분봉:  {analysis.get('reason_5m', '')}")
            else:
                print(f"  → SKIP")

            time.sleep(0.2)

        return results

    def analyze_candles(
        self,
        stock: Dict[str, Any],
        candles_30m: List[Dict[str, Any]],
        candles_5m: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """alphaswarm의 AnalyzeTradingStrategy 패턴:
        자연어 전략 + 시장 데이터 → LLM → 구조화된 분석 결과.
        """
        trend = stock.get("trend", {})
        trade_amt_eok = stock.get("trade_amount", 0) // 100_000_000

        prompt = f"""{self.strategy.rules}

[종목 정보]
종목명: {stock.get('name', '')} ({stock.get('code', '')})
현재가: {stock.get('price', 0):,}원
거래대금: {trade_amt_eok:,}억원

[수급 현황]
외국인  순매수: {trend.get('foreign', 0):+,}주
기관    순매수: {trend.get('institution', 0):+,}주
프로그램 순매수: {trend.get('program', 0):+,}주

{_format_candles(candles_30m, '30분봉 데이터')}

{_format_candles(candles_5m, '5분봉 데이터')}""".strip()

        result = _call_llm(prompt, self.strategy.model_id)
        if result is None:
            return {
                "recommendation": "SKIP",
                "confidence": 0.0,
                "reason_30m": "LLM 분석 실패",
                "reason_5m":  "LLM 분석 실패",
            }
        return result


# ── 결과 요약 출력 ─────────────────────────────────────────────────────────────
def _print_summary(results: List[Dict[str, Any]]) -> None:
    """최종 결과 요약."""
    print(f"\n{'='*60}")
    print(f"  최종 결과: {len(results)}종목")
    print(f"{'='*60}")

    if not results:
        print("  매수/관심 후보 없음")
        return

    buy_stocks   = [r for r in results if r.get("analysis", {}).get("recommendation") == "BUY"]
    watch_stocks = [r for r in results if r.get("analysis", {}).get("recommendation") == "WATCH"]
    no_analysis  = [r for r in results if "analysis" not in r]  # dry-run

    if buy_stocks:
        print("\n  [BUY] 매수 후보")
        for s in buy_stocks:
            a = s["analysis"]
            print(
                f"    {s['name']}({s['code']})  "
                f"현재가:{s.get('price', 0):,}원  "
                f"신뢰도:{a.get('confidence', 0):.0%}"
            )
            print(f"      30분봉: {a.get('reason_30m', '')}")
            print(f"      5분봉:  {a.get('reason_5m', '')}")

    if watch_stocks:
        print("\n  [WATCH] 관심 종목")
        for s in watch_stocks:
            a = s["analysis"]
            print(
                f"    {s['name']}({s['code']})  "
                f"현재가:{s.get('price', 0):,}원  "
                f"신뢰도:{a.get('confidence', 0):.0%}"
            )

    if no_analysis:
        print("\n  [dry-run] 수급 필터 통과 종목")
        for s in no_analysis:
            t = s.get("trend", {})
            print(
                f"    {s['name']}({s['code']})  "
                f"현재가:{s.get('price', 0):,}원  "
                f"외인:{t.get('foreign', 0):+,} "
                f"기관:{t.get('institution', 0):+,}"
            )


# ── CLI 진입점 ─────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="실시간 종목 스크리너 - KIS API + LLM 분봉 분석",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python realtime_screener.py
  python realtime_screener.py --strategy "30분봉 양봉 3연속이고 5분봉 골든크로스 직후"
  python realtime_screener.py --dry-run
  python realtime_screener.py --top 50 --model claude-haiku-4-5-20251001
""",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        help="커스텀 전략 프롬프트 (미입력 시 기본 전략 사용)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-6",
        help="LLM 모델 ID (기본: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="거래대금 상위 N종목 기준 (기본: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="LLM 분석 없이 수급 필터까지만 실행",
    )
    args = parser.parse_args()

    if not is_available():
        print("[ERROR] KIS API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
        sys.exit(1)

    rules    = args.strategy if args.strategy else DEFAULT_STRATEGY_RULES
    strategy = CandleStrategy(rules=rules, model_id=args.model)
    screener = RealtimeScreener(strategy=strategy)

    results = screener.run(top_n=args.top, dry_run=args.dry_run)
    _print_summary(results)


if __name__ == "__main__":
    main()
