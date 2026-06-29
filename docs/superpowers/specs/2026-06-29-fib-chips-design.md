# Fibonacci 레벨 — 차트 밖 HTML 칩으로 이동

**날짜:** 2026-06-29  
**상태:** 승인됨

## 문제

`HandDrawnChartRenderer`가 Fibonacci 레벨 박스를 matplotlib 텍스트 박스로 차트 이미지 안에 그린다. 가격 라인과 겹치고, 이미지 내에 고정되어 있어 스타일 조정이 어렵다.

## 해결 방향

Fib 렌더링을 matplotlib에서 제거하고, API 응답에 Fib 데이터를 추가하여 `detail.html`에서 HTML 칩 한 줄로 표시한다.

## 변경 범위

### 1. `handdrawn_renderer.py`

- `__init__` 파라미터 `show_fib: bool = True` 제거
- `self._show_fib` 필드 제거
- Fib 텍스트 박스 렌더링 블록 전체 제거 (주석 `⑤ Fibonacci 텍스트 박스` 시작 ~60줄)

### 2. `web_app/app.py`

`_compute_four_axis_payload` 함수 내부, `renderer = HandDrawnChartRenderer(...)` 호출 전:

```python
# Fib 레벨 계산 (렌더러에서 뺀 뒤 payload로 전달)
_fib_levels = None
if hist is not None and len(hist) > 1:
    _h_max = float(hist["High"].max())
    _h_min = float(hist["Low"].min())
    _lvls = [
        (0.236, "23%", False),
        (0.382, "38%", True),
        (0.5,   "50%", True),
        (0.618, "62%", True),
        (0.786, "79%", False),
    ]
    _fib_levels = [
        {"pct": sym, "price": round(_h_min + (_h_max - _h_min) * r, 2), "key": key}
        for r, sym, key in _lvls
    ]
```

`HandDrawnChartRenderer(...)` 호출에서 `show_fib=True` 제거.

`payload` dict에 추가:
```python
"fib_levels": _fib_levels,  # None 또는 5개 항목 리스트
```

### 3. `web_app/templates/detail.html`

`#fouraxis-chart-wrap` 닫는 태그 바로 다음에 삽입:

```html
<!-- Fibonacci 칩 -->
<div id="fib-chips" style="display:none; padding:6px 0 2px; gap:6px; flex-wrap:wrap; align-items:center;">
  <span style="font-size:11px; font-weight:700; color:var(--text-secondary);">Fib 120d</span>
</div>
```

차트 로드 JS (기존 `fouraxis-chart` img src 세팅 코드 근처)에 추가:

```js
// Fib 칩 렌더
const fibWrap = document.getElementById('fib-chips');
if (data.fib_levels && data.fib_levels.length) {
  fibWrap.innerHTML = '<span style="font-size:11px;font-weight:700;color:var(--text-secondary);">Fib 120d</span>';
  data.fib_levels.forEach(f => {
    const chip = document.createElement('span');
    chip.textContent = `${f.pct}  ${f.price.toLocaleString()}`;
    chip.style.cssText = f.key
      ? 'background:#ede9fe;color:#7c3aed;border-radius:20px;padding:3px 10px;font-size:11px;font-weight:600;'
      : 'background:#f1f0ff;color:#aaa;border-radius:20px;padding:3px 10px;font-size:11px;';
    fibWrap.appendChild(chip);
  });
  fibWrap.style.display = 'flex';
}
```

## 데이터 구조

```json
"fib_levels": [
  {"pct": "23%", "price": 935.6,  "key": false},
  {"pct": "38%", "price": 989.1,  "key": true},
  {"pct": "50%", "price": 1032.0, "key": true},
  {"pct": "62%", "price": 1076.0, "key": true},
  {"pct": "79%", "price": 1137.0, "key": false}
]
```

`fib_levels`가 `null`이면 `#fib-chips`는 숨김 유지.

## 완료 기준

- 차트 이미지에 Fib 박스가 더 이상 렌더링되지 않음
- 차트 하단에 5개 칩(23·38·50·62·79%)이 표시됨
- 38·50·62%는 보라색, 23·79%는 회색
- Fib 데이터 없는 종목에서 칩 영역이 노출되지 않음
- 기존 테스트 통과
