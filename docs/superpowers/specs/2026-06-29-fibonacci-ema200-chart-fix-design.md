# 4축 차트 피보나치 가격 표시 & EMA200 구분 개선

## 문제

1. **피보나치 가격 미표시**: 차트 우측 레이블이 `F38` 등 약어만 표시되어 실제 가격을 알 수 없음
2. **EMA200 vs 피보나치 시각 혼동**: EMA200(보라 점선)과 피보나치 선(보라 계열 점선)이 색상·스타일 모두 유사해 구분 불가

## 변경 범위

파일: `handdrawn_renderer.py`

### 변경 1 — 피보나치 레이블에 가격 병기

**위치**: `fib_sym` 딕셔너리 정의 후 `ax_price.text()` 호출부 (약 313번째 줄)

```python
# Before
ax_price.text(1.01, fib_price, fib_sym[lvl], ...)

# After
fib_label = f"{fib_sym[lvl]}\n{_fmt_fib(fib_price)}"
ax_price.text(1.01, fib_price, fib_label, ...)
```

레이블 예시: `F38` → `F38\n42,500`

### 변경 2 — EMA200 색상 교체

**위치**: EMA 선 정의 리스트 (약 261번째 줄)

```python
# Before
("EMA200", "#721FE5", 1.2 * lw_scale, (6, 4)),

# After
("EMA200", "#E05A00", 1.2 * lw_scale, (6, 4)),
```

보라(`#721FE5`) → 주황갈색(`#E05A00`). 범례 자동 반영.

## 결과

- 피보나치 수평선 우측에 레벨명과 실제 가격이 함께 표시됨
- EMA200이 주황갈색 점선으로 피보나치 보라 계열과 명확히 구분됨
- 변경 범위: 2줄, 사이드이펙트 없음
