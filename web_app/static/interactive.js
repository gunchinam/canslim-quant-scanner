/**
 * interactive.js — (.)(.)검색기 마이크로인터랙션 모듈
 * app.js와 분리하여 로드 실패 시에도 핵심 기능에 영향 없음.
 *
 * 기능:
 *  1) 점수 게이지 카운트업 애니메이션
 *  2) 퀵필터 전환 카운트 롤링 + confetti
 *  3) "오늘의 발견" 하이라이트 카드
 */

(function () {
  'use strict';

  /* ── prefers-reduced-motion 존중 ─────────────────────────── */
  const prefersReducedMotion = () =>
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ══════════════════════════════════════════════════════════════
   *  1. 점수 게이지 카운트업 애니메이션
   * ══════════════════════════════════════════════════════════════ */

  function easeOutExpo(t) {
    return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t);
  }

  /**
   * 숫자를 from → to 로 카운트업 애니메이션.
   * @param {HTMLElement} el  — textContent 를 교체할 요소
   * @param {number} to      — 목표 숫자
   * @param {number} dur     — ms (기본 600)
   * @param {string} suffix  — 숫자 뒤에 붙일 텍스트 (선택)
   */
  function animateCount(el, to, dur, suffix) {
    if (!el || prefersReducedMotion()) {
      if (el) el.textContent = to + (suffix || '');
      return;
    }
    dur = dur || 600;
    const from = 0;
    let start = null;
    function step(ts) {
      if (!start) start = ts;
      const t = Math.min((ts - start) / dur, 1);
      const val = Math.round(from + (to - from) * easeOutExpo(t));
      el.textContent = val + (suffix || '');
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  /**
   * score-bar-fill 의 width 를 0→목표% 로 애니메이션.
   * CSS transition 을 활용하므로 0% 세팅 후 rAF 로 목표 설정.
   */
  function animateBar(barEl, targetPct) {
    if (!barEl || prefersReducedMotion()) return;
    barEl.style.transition = 'none';
    barEl.style.width = '0%';
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        barEl.style.transition = 'width 0.7s cubic-bezier(0.34, 1.56, 0.64, 1)';
        barEl.style.width = targetPct + '%';
      });
    });
  }

  /**
   * 테이블 렌더 후 뷰포트에 보이는 행의 점수를 카운트업.
   * IntersectionObserver 로 뷰포트 내 행만 애니메이션.
   */
  function observeScoreBars() {
    var tbody = document.getElementById('stock-list');
    if (!tbody || prefersReducedMotion()) return;

    var rows = tbody.querySelectorAll('tr');
    if (!rows.length) return;

    // 이미 관찰 중인 옵저버가 있으면 해제
    if (window._ixScoreObs) {
      window._ixScoreObs.disconnect();
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var row = entry.target;
        observer.unobserve(row);

        var numEl = row.querySelector('.score-num');
        var barEl = row.querySelector('.score-bar-fill');
        if (numEl) {
          var score = parseInt(numEl.textContent, 10) || 0;
          animateCount(numEl, score, 500);
        }
        if (barEl) {
          var w = parseFloat(barEl.style.width) || 0;
          animateBar(barEl, w);
        }
      });
    }, { threshold: 0.1 });

    rows.forEach(function (row) { observer.observe(row); });
    window._ixScoreObs = observer;
  }

  /* ══════════════════════════════════════════════════════════════
   *  2. 퀵필터 전환 카운트 롤링 + Confetti
   * ══════════════════════════════════════════════════════════════ */

  // setStatHTML 을 래핑하여 숫자 변화 시 롤링 애니메이션
  var _prevStatTotal = null;
  var _prevStatStrong = null;

  function animateStatRoll(id, newVal) {
    var el = document.getElementById(id);
    if (!el || prefersReducedMotion()) return;

    // newVal 에서 숫자 추출
    var num = parseInt(newVal, 10);
    if (isNaN(num)) return;

    // 이전 값과 같으면 스킵
    var prevRef = id === 'stat-total' ? _prevStatTotal : _prevStatStrong;
    if (prevRef === num) return;

    if (id === 'stat-total') _prevStatTotal = num;
    else _prevStatStrong = num;

    // 롤 애니메이션: 위로 슬라이드-아웃 후 새 값 슬라이드-인
    el.classList.add('ix-stat-roll');
    setTimeout(function () {
      el.classList.remove('ix-stat-roll');
    }, 350);
  }

  /**
   * CSS-only Confetti 파티클 효과.
   * @param {HTMLElement} anchor — 파티클이 터질 기준 요소
   * @param {number} count      — 파티클 수 (기본 12)
   */
  function confetti(anchor, count) {
    if (!anchor || prefersReducedMotion()) return;
    count = count || 12;

    var rect = anchor.getBoundingClientRect();
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;

    var colors = ['#3182F6', '#00C073', '#FF9200', '#F04452', '#A855F7'];
    var container = document.createElement('div');
    container.className = 'ix-confetti-container';
    container.setAttribute('aria-hidden', 'true');

    for (var i = 0; i < count; i++) {
      var dot = document.createElement('span');
      dot.className = 'ix-confetti-dot';
      var angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.5;
      var dist = 30 + Math.random() * 50;
      var dx = Math.cos(angle) * dist;
      var dy = Math.sin(angle) * dist - 20;
      dot.style.setProperty('--ix-dx', dx + 'px');
      dot.style.setProperty('--ix-dy', dy + 'px');
      dot.style.left = cx + 'px';
      dot.style.top = cy + 'px';
      dot.style.background = colors[i % colors.length];
      dot.style.animationDelay = (Math.random() * 80) + 'ms';
      container.appendChild(dot);
    }

    document.body.appendChild(container);
    setTimeout(function () { container.remove(); }, 900);
  }

  /**
   * 강력매수 종목이 많을 때 confetti 트리거.
   * stat-strong 업데이트 시 호출.
   */
  function maybeConfetti(strongCount, totalCount) {
    if (prefersReducedMotion()) return;
    // 전체의 25% 이상이 강력매수이거나 5개 이상
    if (totalCount > 0 && (strongCount >= 5 || strongCount / totalCount >= 0.25)) {
      var el = document.getElementById('stat-strong');
      if (el) confetti(el, 15);
    }
  }

  /* ══════════════════════════════════════════════════════════════
   *  3. "오늘의 발견" 하이라이트 카드
   * ══════════════════════════════════════════════════════════════ */

  function renderDiscoveryCard(stocks) {
    var card = document.getElementById('ix-discovery-card');
    if (!card || !Array.isArray(stocks) || stocks.length === 0) {
      if (card) card.style.display = 'none';
      return;
    }

    // 후보 1: 점수 급등 (ScoreDelta 최고)
    var topDelta = null;
    var topDeltaVal = -Infinity;
    // 후보 2: 신규 진입 (IsNew)
    var newEntry = null;
    // 후보 3: 강한 시그널 + 최고 점수
    var topStrong = null;

    stocks.forEach(function (s) {
      var delta = s.ScoreDelta || 0;
      if (delta > topDeltaVal && delta > 1) {
        topDeltaVal = delta;
        topDelta = s;
      }
      if (s.IsNew && !newEntry) newEntry = s;
      if (!topStrong && typeof s.Signal === 'string' &&
          (s.Signal.toUpperCase().includes('BREAKOUT') ||
           s.Signal.toUpperCase().includes('STRONG LEADER'))) {
        topStrong = s;
      }
    });

    // 우선순위: 점수 급등 > 신규 진입 > 강한 시그널
    var pick = topDelta || newEntry || topStrong;
    if (!pick) {
      card.style.display = 'none';
      return;
    }

    var reason = '';
    var icon = '';
    if (pick === topDelta) {
      icon = '<span class="ix-disc-icon ix-disc-fire">&#x1F525;</span>';
      reason = '점수 &#x25B2;' + topDeltaVal.toFixed(1) + ' 급등';
    } else if (pick === newEntry) {
      icon = '<span class="ix-disc-icon ix-disc-new">NEW</span>';
      reason = '신규 진입 종목';
    } else {
      icon = '<span class="ix-disc-icon ix-disc-breakout">&#x1F4C8;</span>';
      reason = (pick.Signal || '').replace(/_/g, ' ');
    }

    var score = Math.round(pick.TotalScore || 0);
    var sc = score >= 70 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low';
    var dayChg = pick.DayChg || 0;
    var chgPct = (dayChg * 100).toFixed(2);
    var chgClass = dayChg > 0 ? 'chg-up' : dayChg < 0 ? 'chg-down' : 'chg-flat';
    var chgSign = dayChg > 0 ? '+' : '';

    var nameEsc = (pick.Name || pick.Ticker || '').replace(/[<>&"]/g, function (c) {
      return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c];
    });
    var tickerEsc = (pick.Ticker || '').replace(/[<>&"]/g, function (c) {
      return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c];
    });

    card.innerHTML =
      '<div class="ix-disc-inner" onclick="openDetail(\'' + tickerEsc + '\')" style="cursor:pointer;">' +
        '<div class="ix-disc-badge">' + icon + '<span class="ix-disc-reason">' + reason + '</span></div>' +
        '<div class="ix-disc-main">' +
          '<span class="ix-disc-name">' + nameEsc + '</span>' +
          '<span class="ix-disc-ticker">' + tickerEsc + '</span>' +
          '<span class="ix-disc-score ' + sc + '">' + score + '점</span>' +
          '<span class="ix-disc-chg ' + chgClass + '">' + chgSign + chgPct + '%</span>' +
        '</div>' +
        '<div class="ix-disc-label">오늘의 발견</div>' +
      '</div>';

    card.style.display = '';

    // 카드 슬라이드-인 애니메이션
    if (!prefersReducedMotion()) {
      card.classList.remove('ix-disc-enter');
      void card.offsetWidth; // reflow
      card.classList.add('ix-disc-enter');
    }
  }

  /* ══════════════════════════════════════════════════════════════
   *  훅: app.js 의 기존 함수를 래핑
   * ══════════════════════════════════════════════════════════════ */

  function hookIntoApp() {
    // 1) setStatHTML 래핑 → 카운트 롤링 애니메이션
    if (typeof window.setStatHTML === 'function') {
      var _origSetStatHTML = window.setStatHTML;
      window.setStatHTML = function (id, html) {
        _origSetStatHTML(id, html);
        if (id === 'stat-total' || id === 'stat-strong') {
          animateStatRoll(id, html);
        }
      };
    }

    // 2) renderStockTable 래핑 → score 카운트업 + 오늘의 발견
    if (typeof window.renderStockTable === 'function') {
      var _origRenderStockTable = window.renderStockTable;
      window.renderStockTable = function (stocks) {
        _origRenderStockTable(stocks);

        // 점수 바 애니메이션
        requestAnimationFrame(function () {
          observeScoreBars();
        });

        // 오늘의 발견 카드
        var all = window._scanStocks || window.allStocks || stocks || [];
        renderDiscoveryCard(all);

        // confetti 판단
        if (Array.isArray(stocks)) {
          var total = stocks.length;
          var strong = 0;
          stocks.forEach(function (s) {
            if (s.Signal && (
              s.Signal.toUpperCase().includes('BREAKOUT') ||
              s.Signal.toUpperCase().includes('STRONG LEADER') ||
              s.Signal.toUpperCase().includes('MOMENTUM')
            )) strong++;
          });
          maybeConfetti(strong, total);
        }
      };
    }

    // 3) 퀵필터 칩 클릭 시 롤링 효과 강화
    var chips = document.getElementById('filter-chips');
    if (chips) {
      chips.addEventListener('click', function () {
        _prevStatTotal = null;
        _prevStatStrong = null;
      });
    }
  }

  /* ── 초기화 ──────────────────────────────────────────────── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hookIntoApp);
  } else {
    hookIntoApp();
  }

})();
