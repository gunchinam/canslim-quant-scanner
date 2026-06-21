---
name: regime-alert
description: This skill should be used when the user asks about "레짐", "시장 국면", "현금화", "풀시드", "포지션 변경", "regime", "레짐 확인", "레짐 알림", "지금 들어가도 돼?", "지금 빠져야 해?". Use proactively when the user asks whether to enter or exit the market. Make sure to use this skill whenever the user mentions market timing, regime, or position sizing — even if they don't explicitly ask for it.
---

# 레짐 알림 스킬

> KOSPI 시장 국면(레짐)을 선제적으로 판단해 전액 현금화 또는 풀시드 진입 권고 알림을 발송한다.

## 워크플로우

### Step 1: 레짐 분석 스크립트 실행
**타입**: script

프로젝트 루트에서 실행:

```bash
python skills/regime-alert/scripts/regime_alert.py
```

Windows PowerShell:
```powershell
python skills\regime-alert\scripts\regime_alert.py
```

종료 코드 의미:
- `0` — 현상 유지 (액션 없음)
- `1` — `early_exit` 감지 → 전액 현금화 권고
- `2` — `early_long` 감지 → 풀시드 진입 권고

### Step 2: 결과 해석 및 보고
**타입**: prompt

스크립트 출력을 읽고 사용자에게 한 줄로 요약한다:
- 현재 레짐과 확신도
- 선행 신호 유무 및 강도
- 내일 Bear/Bull 확률
- 권고 액션 (현금화 / 풀시드 / 유지)

## 레짐 정의

| 레짐 | 의미 | 기본 포지션 |
|------|------|------------|
| `low_vol_uptrend` | 저변동 상승장 (Bull) | 풀시드 |
| `high_vol_downtrend` | 고변동 하락장 (Bear) | 전액 현금 |
| `range_chop` | 횡보 (Chop) | 50% 이하 보수 운용 |

## 선행 신호 (early signal) — 선제적 판단의 핵심

| 신호 | 조건 | 권고 액션 |
|------|------|----------|
| `early_long` | Bear/Chop 상태이지만 Bull 확률이 2일 연속 상승 + 임계 돌파 | 풀시드 선제 진입 |
| `early_exit` | Bull 상태이지만 Bear 확률이 2일 연속 상승 + 임계 돌파 | 선제 전액 현금화 |

## 자동화 (GitHub Actions)

매일 08:30 KST에 자동 실행 → `.github/workflows/daily_briefing.yml`

수동 테스트:
```bash
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python skills/regime-alert/scripts/regime_alert.py
```

## 환경 변수

| 변수 | 설명 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 수신 채팅 ID |
