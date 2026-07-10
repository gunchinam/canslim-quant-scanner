# 판단 포스터 한줄평 헤드라인 레이아웃 재설계 -- 프로젝트 스펙

> AI가 코드를 짤 때 지켜야 할 규칙과 절대 하면 안 되는 것.

---

## 기술 스택

| 영역 | 선택 | 이유 |
|------|------|------|
| 백엔드 | Flask (기존) | 변경 없음, `d.OneLiner` 필드는 이미 존재 |
| 프론트 | Vanilla JS(`app.js`) + Jinja 템플릿(`scanner.html`) | 기존 스택 그대로, 새 프레임워크 도입 없음 |
| 스타일링 | 순수 CSS(`scanner.css`) | 기존 스택 그대로, clamp()/미디어쿼리 등 표준 CSS만 사용 |

---

## 관련 파일 (프로젝트 구조)

```
web_app/
├── static/
│   ├── app.js            # _renderEntryVerdict(d) 함수, _pvWord/_dvpWordPx/_dhbWordPx 계산(약 3593~3790줄)
│   └── scanner.css        # .dp-verdict-poster/.dvp-word(모바일, 약 2578~2632줄),
│                           # .dhb-verdict/.dhb-word(데스크톱, 약 3900~3960줄)
├── templates/
│   └── scanner.html       # dp-verdict-poster, dp-hero-banner-dt 마크업(259~260줄)
├── one_liner.py            # OneLiner 문구 풀 -- 이번 골에서 변경 안 함
└── app.py                  # _annotate_one_liners -- 이번 골에서 변경 안 함
```

---

## 절대 하지 마 (DO NOT)

- [ ] `_pgCls`(배경색 등급), `conv`(확신도 계산) 로직을 변경하지 마 -- 이번 골 범위 밖.
- [ ] `_pvReason`(3줄 이유 문구 풀)을 변경하지 마 -- 이번 골 범위 밖.
- [ ] `one_liner.py`의 `_PHRASES`(문구 자체)를 변경하지 마 -- 직전 골에서 이미 완료된 영역.
- [ ] `d.OneLiner`를 텍스트로 렌더링할 때 `esc()` 없이 직접 삽입하지 마(XSS 방지, 기존 `esc(d.OneLiner)` 패턴 유지).
- [ ] 텍스트를 자르거나(`text-overflow:ellipsis` 등으로 잘라내거나) `max-length`로 제한하지 마 -- 사용자가 "길이 그대로 다 보이게"를 이전 골에서 명시적으로 요구했고, 이번 골도 그 원칙을 유지한다.
- [ ] 모바일/데스크톱 중 한쪽만 고치고 다른 쪽을 방치하지 마 -- 두 레이아웃 모두 이번 골의 성공 기준 대상이다.
- [ ] 기존 pytest 베이스라인(V5: 2 failed/24 passed, V6: 195 passed)을 깨뜨리지 마.

---

## 항상 해 (ALWAYS DO)

- [ ] 레이아웃을 바꾸기 전에 현재 CSS/JS 코드(줄 번호 포함)를 먼저 읽고 정확한 위치를 파악해.
- [ ] 짧은 한줄평(15자 내외)과 긴 한줄평(35~40자) 두 극단 모두로 테스트해.
- [ ] 폰트 크기 변경 시 실제 렌더링 결과(스크린샷 또는 브라우저 확인)로 검증하고, 코드만 보고 "될 것 같다"로 통과 처리하지 마.
- [ ] 모바일 반응형(기존 미디어쿼리 브레이크포인트) 유지.

---

## 테스트 방법

```bash
# 저장소 루트에서
python3 -m pytest tests/test_one_liner_consistency.py -q
python3 -m pytest web_app/tests/ -q --deselect web_app/tests/test_history_timeline.py

# 로컬 서버로 육안 확인
cd web_app && python3 app.py   # 이후 브라우저로 드로워 열어 판단 포스터 확인
```

---

## [NEEDS CLARIFICATION]

- 없음.
