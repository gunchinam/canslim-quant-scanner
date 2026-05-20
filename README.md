# canslim-quant-scanner

> "좋은 회사인가"와 "지금 들어갈 자리인가"를 동시에 답하는 미국/한국 주식 스캐너.
>
> CAN SLIM 원칙 + 퀀트 팩터 + 진입 타이밍 점수를 한 화면에 묶어, 스캔부터 진입 판단까지 한 곳에서 끝냅니다.

![home](docs/post_images/01_home.png)

## Features

- **CAN SLIM 기반 종목 평가** — 실적, 수급, 모멘텀을 종합 점수로 환산
- **미국 + 한국 주식 동시 스캔** — Yahoo Finance · KIS · DART · Finnhub 데이터 통합
- **진입 타이밍 카드** — 진입가, 손절가, 목표가를 한눈에 제시
- **한줄평 코멘트** — 주갤 커뮤니티 톤의 2,600+ 구문 풀에서 종목별 한 줄 평가
- **매크로 스트립** — 금리, 환율, VIX 등 거시 지표를 상단에 실시간 요약
- **실시간 채팅** — WebSocket 기반 익명 채팅으로 종목 토론
- **로컬 API 관리** — `/settings`에서 API 키 설정, `/healthz`로 서버 상태 확인

## Current UI

### 홈 화면

![home-ui](docs/post_images/01_home.png)

현재 홈 화면에는 다음이 반영되어 있습니다.

- 상단 매크로 스트립: 시장 상태, 금리, 환율, VIX 같은 거시 지표를 빠르게 확인
- 스캔 테이블: 종합 점수, 진입 상태, 브로커 목표가, 핵심 이유를 한 줄로 요약

### 종목 상세 화면

![detail-ui](docs/post_images/02_detail_nvda.png)

상세 화면은 예전보다 "무슨 행동을 해야 하는지"가 먼저 보이도록 정리했습니다.

- 진입 타이밍 카드가 `결론 / 행동 / 더보기` 구조로 정리됨
- `진입가 / 손절 / 목표가1`를 먼저 보여주고 나머지는 접어서 표시
- 종합 점수와 진입 타이밍을 함께 보는 2축 사분면 추가
- 별점 영역은 차트 타이밍용, 종합 점수는 회사/종목 평가용으로 역할을 분리

### 종목 비교 화면

![compare-ui](docs/post_images/03_compare_nvda_msft_amzn.png)

비교 화면에서는 종목 간 점수와 톤 차이를 빠르게 볼 수 있습니다.

### 설정 화면

![settings-ui](docs/post_images/04_settings.png)

`/settings`에서는 로컬 `config.json` 기반으로 API 키와 토큰을 저장할 수 있습니다.

### 헬스체크

![healthz-ui](docs/post_images/05_healthz.png)

배포 후에는 `/healthz`로 서버 상태를 빠르게 확인할 수 있습니다.

## Entry Timing

이 프로젝트의 진입 타이밍 점수는 "좋은 회사인가"와 "지금 들어갈 자리인가"를 분리해서 봅니다.

- 종합 점수: 회사/종목의 전반적 질과 매력도
- 진입 타이밍: 지금 매수해도 되는 자리인지

현재 UI에서는 이 차이를 더 명확하게 보여주기 위해 다음을 반영했습니다.

- 진입 카드 헤드라인을 더 크게 표시
- 보조 사유를 별도 줄로 분리
- 가격 액션에서 가장 중요한 3개 숫자만 먼저 노출
- 점수 분해와 AgentQuant 근거는 펼쳤을 때만 확인

## Quick Start

### Requirements

- Python 3.11+
- Windows, macOS, Linux
- 선택 사항: KIS, DART, Finnhub, Telegram 등 외부 API

### 로컬 실행

```bash
git clone https://github.com/gunchinam/canslim-quant-scanner.git
cd canslim-quant-scanner
pip install -r requirements.txt
python -m web_app.app
```

브라우저에서 `http://127.0.0.1:5000`으로 접속하면 됩니다.

### Docker 실행

```bash
# .env 파일에 API 키 설정 (선택)
cp .env.example .env

# 빌드 & 실행
docker compose up --build
```

`http://localhost:8000`으로 접속합니다.

## Configuration

- 로컬 설정 화면: `/settings`
- 로컬 설정 파일: `config.json`
- 공개용 예시 파일: `config.example.json`

실제 API 키, 토큰, 계좌번호는 공개 저장소에 넣지 않는 전제로 동작합니다.

## Deployment

### Docker (권장)

```bash
docker compose up -d --build
```

- **포트**: 8000 (docker-compose.yml에서 변경 가능)
- **환경변수**: `.env` 파일에서 API 키 주입
- **영속 데이터**: `app-data`, `yfinance-cache` 볼륨으로 자동 관리
- **헬스체크**: 30초 간격 자동 확인, 실패 시 5회까지 재시작

### Render

- `render.yaml` 포함
- 시작 명령: `gunicorn --bind 0.0.0.0:$PORT wsgi:app`
- 운영 환경에서는 실제 비밀값을 Render 환경변수로 넣는 편이 맞음

### Oracle Cloud

- [Oracle Cloud 가이드](deploy/ORACLE_CLOUD.md)
- [초기 세팅 스크립트](deploy/setup-oracle.sh)

## Public Repo Notes

- 실제 비밀값은 `.env` 또는 로컬 `config.json`에만 저장
- `config.example.json`만 커밋하고 `config.json`은 커밋하지 않음
- 토큰 캐시, 로컬 UI 상태, 데이터 산출물은 `.gitignore`로 제외
- `data/`, `*.parquet`, `.kis_token_cache.json`, `_*.json` 같은 로컬 산출물은 공개 제외

## Tests

```bash
pytest tests/test_entry_status_v2.py tests/test_entry_status_v3.py
```

## License

[MIT License](LICENSE)
