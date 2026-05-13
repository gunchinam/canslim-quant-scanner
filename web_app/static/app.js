/**
 * app.js — (.)(.)검색기 웹 프론트엔드
 * scanner.html (데스크탑 테이블) / detail.html 공용 스크립트
 */

// ── 상태 ─────────────────────────────────────────────────────────────────
let currentMarket   = 'US';
let currentStrategy = 'BALANCED';
let currentSector   = '';   // '' = 전체
let allStocks       = [];   // 마지막 스캔 결과 캐시
let _cachedGroups   = {};   // loadSectors 결과 보관 (sidebar 재렌더용)
let _cachedSectors  = {};   // loadSectors 결과 보관
let _sortKey        = 'TotalScore';  // 현재 정렬 키 (기본: 복합 점수)
let _sortDir        = -1;   // 0=없음, 1=asc, -1=desc
let _stockMap       = {};   // ticker → stock data (팝업용)
let _currentFilter  = 'all'; // 활성 퀵필터: all/watchlist/strong/near_high/oversold/intraday
let _watchlist      = new Set(); // 현재 마켓의 워치리스트 티커 집합

// ── 워치리스트 (localStorage) ───────────────────────────────────────────
function _wlKey(market) { return `scanner_watchlist_${market || currentMarket}`; }
function loadWatchlist(market) {
  try {
    const raw = localStorage.getItem(_wlKey(market));
    _watchlist = new Set(raw ? JSON.parse(raw) : []);
  } catch { _watchlist = new Set(); }
}
function saveWatchlist() {
  try { localStorage.setItem(_wlKey(), JSON.stringify([..._watchlist])); } catch {}
}
function toggleWatchlist(ticker, ev) {
  if (ev) { ev.stopPropagation(); }
  if (_watchlist.has(ticker)) _watchlist.delete(ticker);
  else _watchlist.add(ticker);
  saveWatchlist();
  _refreshFilteredView();
}

// ── 공통 유틸 ────────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function scoreClass(score) {
  if (score >= 70) return 'score-high';
  if (score >= 50) return 'score-mid';
  return 'score-low';
}

function _signalTier(signal) {
  if (!signal) return 'neutral';
  const s = signal.toUpperCase();
  if (s.includes('BREAKOUT') || s.includes('STRONG LEADER') || s.includes('MOMENTUM')) return 'strong';
  if (s.includes('LEADER') || s.includes('WATCH') || s.includes('ACCUMULATE')) return 'buy';
  if (s.includes('NEUTRAL') || s.includes('HOLD')) return 'hold';
  if (s.includes('SELL') || s.includes('AVOID') || s.includes('LAGGARD') || s.includes('BEAR') || s.includes('CAUTION')) return 'sell';
  return 'neutral';
}

function signalColor(signal) {
  const tier = _signalTier(signal);
  return { strong: 'var(--success)', buy: 'var(--info)', hold: 'var(--warning)', sell: 'var(--destructive)', neutral: 'var(--text-secondary)' }[tier];
}

function signalBg(signal) {
  const tier = _signalTier(signal);
  return { strong: 'rgba(0,192,115,0.10)', buy: 'rgba(49,130,246,0.10)', hold: 'rgba(255,146,0,0.10)', sell: 'rgba(240,68,82,0.10)', neutral: 'var(--surface-subtle)' }[tier];
}

// 시그널 문자열에서 메인 시그널과 [태그]를 분리
function _splitSignal(signal) {
  if (!signal) return { base: signal, tags: [] };
  const tags = [];
  const base = signal.replace(/\s*\u{1F514}?\[([^\]]+)\]/gu, (_, tag) => {
    tags.push(tag);
    return '';
  }).trim();
  return { base, tags };
}

const _TAG_KO = {
  'BREAKOUT':'돌파','PIVOT':'피벗','TREND':'추세',
  'EPS':'EPS','VOL':'거래량','LOW LIQ':'유동성↓',
};

function _renderEntryCard(d) {
  const card = document.getElementById('dp-entry-card');
  if (!card) return;
  card.classList.remove('green', 'yellow', 'red');
  const st = d.EntryStatus || '';
  const ico = st === 'GREEN' ? '🟢' : st === 'YELLOW' ? '🟡' : st === 'RED' ? '🔴' : '⚪';
  const score = d.EntryScore != null ? Math.round(d.EntryScore) : null;
  const phrase = d.EntryPhrase || '—';
  const plan = d.EntryPlan || {};
  setText('dp-entry-icon', ico);
  setText('dp-entry-phrase', phrase);
  setText('dp-entry-score', score != null ? String(score) : '—');
  const fill = document.getElementById('dp-entry-bar-fill');
  if (fill) fill.style.width = (score != null ? Math.max(0, Math.min(100, score)) : 0) + '%';
  if (st) card.classList.add(st.toLowerCase());
  setText('dp-entry-px-entry', plan.entry != null ? fmtPrice(plan.entry) : '—');
  setText('dp-entry-px-stop',  plan.stop  != null ? fmtPrice(plan.stop)  : '—');
  setText('dp-entry-px-t1',    plan.t1    != null ? fmtPrice(plan.t1)    : '—');
  setText('dp-entry-px-t2',    plan.t2    != null ? fmtPrice(plan.t2)    : '—');
}

function _entryLight(stock) {
  if (!stock || !stock.EntryStatus) return '';
  const st = stock.EntryStatus;
  const ico = st === 'GREEN' ? '🟢' : st === 'YELLOW' ? '🟡' : '🔴';
  const phr = stock.EntryPhrase || '';
  const sc  = stock.EntryScore != null ? `진입 타이밍 ${stock.EntryScore}/100` : '';
  const tip = phr ? `${phr}${sc ? ' (' + sc + ')' : ''}` : sc;
  return `<span class="entry-light" title="${esc(tip)}">${ico}</span>`;
}

function _renderSignalHtml(signal, stock) {
  const { base, tags } = _splitSignal(signal);
  const tr = _trKo(base || '—');
  let h = `<div class="signal-row">${_entryLight(stock)}<span class="signal-badge" style="color:${signalColor(base)};background:${signalBg(base)}">${esc(tr)}</span></div>`;
  if (tags.length) {
    h += '<div class="signal-tags">';
    for (const t of tags) {
      const clean = t.replace(/[\u{1F525}\u{1F514}]/gu, '').trim();
      const label = _TAG_KO[clean] || clean;
      const cls = /BREAKOUT|EPS|VOL/.test(t) ? 'sig-tag-hot' : /LOW|LIQ/.test(t) ? 'sig-tag-warn' : 'sig-tag-info';
      h += `<span class="sig-tag ${cls}">${esc(label)}</span>`;
    }
    h += '</div>';
  }
  return h;
}

function fmt(v, digits = 0) {
  if (v === null || v === undefined) return '—';
  return Number(v).toFixed(digits);
}

function fmtPrice(v) {
  if (!v) return '—';
  const n = Number(v);
  if (n >= 1000) return n.toLocaleString('ko-KR', { maximumFractionDigits: 0 });
  return n.toFixed(2);
}

// ── 마켓/전략 변경 (scanner.html select) ─────────────────────────────────

function _setSegActive(groupId, val) {
  document.querySelectorAll(`#${groupId} .btn-seg`).forEach(b => {
    b.classList.toggle('active', b.dataset.val === val);
  });
}

function onMarketChange(val) {
  currentMarket = val;
  currentSector = '';
  allStocks     = [];
  loadWatchlist();
  _setSegActive('market-btn-group', val);
  loadSectors();
  setStockListMsg('섹터를 선택하거나 스캔 버튼을 눌러주세요.');
  setStatHTML('stat-total',  '—<span class="unit">개</span>');
  setStatHTML('stat-strong', '—<span class="unit">개</span>');
  setText('stat-sector', '전체');
}

// 전략 토글 제거됨 — 5개 전략 점수를 한 번에 표시하고 컬럼 헤더 클릭으로 정렬
function onStrategyChange(_val) { /* deprecated */ }

// 중첩 키 접근 ("Scores.BALANCED" → obj.Scores?.BALANCED)
function _getByPath(obj, path) {
  if (!obj || !path) return undefined;
  return path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);
}

// ── 스캐너 페이지 ────────────────────────────────────────────────────────

async function loadSectors() {
  try {
    const res  = await fetch(`/api/sectors?market=${currentMarket}`);
    const data = await res.json();
    _cachedGroups  = data.groups  || {};
    _cachedSectors = data.sectors || {};
    renderSectorList(_cachedGroups, _cachedSectors);
  } catch (e) {
    console.error('loadSectors 실패:', e);
  }
}

function renderSectorList(groups, sectors) {
  const list = document.getElementById('filter-list');
  if (!list) return;

  // 전체 스캔 버튼
  const allActive = currentSector === '' ? ' active' : '';
  let html = `<button class="sector-btn-all${allActive}" onclick="selectSector(this,'')">전체 스캔</button>`;

  // 카테고리 그룹 아코디언 (첫 번째 그룹만 자동 열림)
  Object.entries(groups).forEach(([cat, subsectors], idx) => {
    const isOpen   = idx === 0;
    const open     = isOpen ? ' open' : '';
    const chevOpen = isOpen ? ' open' : '';

    html += `
<div class="sector-group">
  <button class="sector-group-header" onclick="toggleGroup(this)">
    <span class="sector-group-label">${esc(cat)}</span>
    <svg class="sector-group-chevron${chevOpen}" width="12" height="12" viewBox="0 0 24 24"
         fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  </button>
  <div class="sector-group-body${open}">`;

    subsectors.forEach(sub => {
      const active = currentSector === sub ? ' active' : '';
      html += `<button class="sector-btn${active}" onclick="selectSector(this,'${esc(sub)}')">
  <span class="sector-btn-label">${esc(sub)}</span>
</button>`;
    });

    html += `</div></div>`;
  });

  list.innerHTML = html;
}

function toggleGroup(headerBtn) {
  const body    = headerBtn.nextElementSibling;
  const chevron = headerBtn.querySelector('.sector-group-chevron');
  const isOpen  = body.classList.contains('open');
  body.classList.toggle('open', !isOpen);
  chevron.classList.toggle('open', !isOpen);
}

function selectSector(btn, sector) {
  currentSector = sector;
  // 모든 섹터 버튼 비활성화
  document.querySelectorAll('#filter-list .sector-btn, #filter-list .sector-btn-all')
    .forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  setText('stat-sector', sector || '전체');

  const inp = document.getElementById('search-input');
  if (inp) inp.value = '';

  runScan();
}

async function runScan() {
  const btn = document.getElementById('btn-scan');
  if (btn) { btn.disabled = true; }

  setStatHTML('stat-total',  '…<span class="unit">개</span>');
  setStatHTML('stat-strong', '…<span class="unit">개</span>');
  setStockListMsg('스캔 중…');

  try {
    const p = new URLSearchParams({ market: currentMarket, strategy: currentStrategy });
    if (currentSector) p.set('sector', currentSector);

    const res    = await fetch(`/api/scan?${p}`);
    const stocks = await res.json();
    allStocks    = Array.isArray(stocks) ? stocks : [];
    renderStockTable(allStocks);
  } catch (e) {
    console.error('runScan 실패:', e);
    setStockListMsg('스캔 실패. 서버 상태를 확인하세요.');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// 퀵필터 적용
function _applyQuickFilter(stocks) {
  switch (_currentFilter) {
    case 'watchlist':
      return stocks.filter(s => _watchlist.has(s.Ticker));
    case 'entry_green':
      return stocks.filter(s => s.EntryStatus === 'GREEN');
    case 'strong':
      return stocks.filter(s => _signalTier(s.Signal) === 'strong');
    case 'near_high':
      return stocks.filter(s => s.NearHighPass);
    case 'oversold':
      return stocks.filter(s => s.RSI != null && s.RSI < 30);
    case 'intraday':
      return stocks.filter(s =>
        (s.ORBSignal && s.ORBSignal !== 'NEUTRAL' && s.ORBSignal !== '-') ||
        (s.NR7Signal && s.NR7Signal !== 'NEUTRAL' && s.NR7Signal !== '-') ||
        (s.BBSignal  && s.BBSignal  !== 'NEUTRAL' && s.BBSignal  !== '-')
      );
    default: return stocks;
  }
}

// 필터/정렬을 다시 적용해 테이블 갱신
function _refreshFilteredView() {
  renderStockTable(allStocks);
}

function renderStockTable(stocks) {
  const tbody = document.getElementById('stock-list');
  if (!tbody) return;

  // 워치리스트 카운트 (전체 기준)
  const wlEl = document.getElementById('chip-watch-count');
  if (wlEl) wlEl.textContent = stocks.filter(s => _watchlist.has(s.Ticker)).length;

  // 퀵필터 적용
  const filtered = _applyQuickFilter(stocks);

  const strong = filtered.filter(s => _signalTier(s.Signal) === 'strong').length;
  setStatHTML('stat-total',  `${filtered.length}<span class="unit">개</span>`);
  setStatHTML('stat-strong', `${strong}<span class="unit">개</span>`);

  if (filtered.length === 0) {
    const emptyMsg = _currentFilter === 'watchlist'
      ? '워치리스트가 비어있습니다. 표의 ☆ 버튼으로 추가하세요.'
      : '필터 조건에 맞는 종목이 없습니다.';
    tbody.innerHTML = `<tr><td colspan="${_colCount()}" class="state-msg">${esc(_currentFilter === 'all' ? '결과 없음' : emptyMsg)}</td></tr>`;
    return;
  }

  _stockMap = {};
  filtered.forEach(s => { _stockMap[s.Ticker] = s; });
  // 이후 sort 로직에서 사용되는 `stocks` 변수 재할당
  stocks = filtered;

  // 현재 정렬 적용
  let view = stocks;
  if (_sortKey && _sortDir !== 0) {
    view = [...stocks].sort((a, b) => {
      const va = _getByPath(a, _sortKey);
      const vb = _getByPath(b, _sortKey);
      const aa = va == null ? -Infinity : va;
      const bb = vb == null ? -Infinity : vb;
      return _sortDir * (aa > bb ? 1 : aa < bb ? -1 : 0);
    });
  }
  tbody.innerHTML = view.map((s, i) => renderStockRow(s, i + 1)).join('');
}

function _deltaBadge(stock) {
  if (stock && stock.IsNew) {
    return `<span class="score-delta new" title="기준일 이후 새로 진입한 종목">NEW</span>`;
  }
  const d = stock ? stock.ScoreDelta : null;
  if (d == null) return '';
  const days = stock.DeltaDays || 1;
  const rd = stock.RankDelta;
  const rdTxt = rd == null ? '' : (rd > 0 ? ` · 순위 ▲${rd}` : rd < 0 ? ` · 순위 ▼${-rd}` : ' · 순위 —');
  if (d > 0.05) {
    return `<span class="score-delta up" title="${days}일 전 대비 점수 +${d.toFixed(1)}${rdTxt}">▲${d.toFixed(1)}</span>`;
  }
  if (d < -0.05) {
    return `<span class="score-delta down" title="${days}일 전 대비 점수 ${d.toFixed(1)}${rdTxt}">▼${Math.abs(d).toFixed(1)}</span>`;
  }
  return `<span class="score-delta flat" title="${days}일 전 대비 변동 없음${rdTxt}">—</span>`;
}

function renderStockRow(stock, rank) {
  const rankClass  = rank <= 3 ? `rank-${rank}` : 'rank-other';
  const score      = Math.round(stock.TotalScore || 0);
  const sc         = scoreClass(score);
  const barW       = Math.min(100, Math.max(0, score));
  const dayChg     = stock.DayChg || 0;
  const chgPct     = (dayChg * 100).toFixed(2);
  const chgClass   = dayChg > 0 ? 'chg-up' : dayChg < 0 ? 'chg-down' : 'chg-flat';
  const chgSign    = dayChg > 0 ? '+' : '';
  const rsi        = stock.RSI != null ? fmt(stock.RSI, 1) : '—';
  const upsidePct  = stock.TargetUpside != null
    ? (stock.TargetUpside >= 0 ? '+' : '') + fmt(stock.TargetUpside * 100, 1) + '%'
    : '—';
  const upside     = stock.TargetPrice
    ? `<div class="target-price">${fmtPrice(stock.TargetPrice)}</div><div class="target-upside">${upsidePct}</div>`
    : upsidePct;

  // 리스크 배지 HTML
  let riskHtml = '';
  const risks = [];
  if (stock.LowLiquidity) risks.push('<span class="risk-badge risk-badge-liq" title="거래대금 부족 — 유동성이 낮아 매매 시 주의">유동성↓</span>');
  if (stock.FailSafe)     risks.push('<span class="risk-badge risk-badge-fail" title="안전장치 발동 — EPS 적자 또는 RS 40 미만으로 점수 상한 제한">' + (stock._fail_eps ? 'EPS적자' : '안전장치') + '</span>');
  if (stock.BearCap)      risks.push('<span class="risk-badge risk-badge-bear" title="하락장 상한 발동 — 하락장으로 점수 50점 상한 제한">하락장↓</span>');
  if (risks.length) riskHtml = `<div class="risk-badges">${risks.join('')}</div>`;

  // TopReason 태그 HTML
  const reasonHtml = _renderReasonTags(stock.TopReason);

  const starred = _watchlist.has(stock.Ticker);
  return `
<tr onclick="openDetail('${esc(stock.Ticker)}')" style="cursor:pointer;">
  <td class="center"><button class="star-btn${starred ? ' starred' : ''}" onclick="toggleWatchlist('${esc(stock.Ticker)}', event)" title="${starred ? '워치리스트에서 제거' : '워치리스트에 추가'}">${starred ? '★' : '☆'}</button></td>
  <td class="center"><span class="rank-cell ${rankClass}">${rank}</span></td>
  <td class="name-cell" onmouseenter="showStockPopup('${esc(stock.Ticker)}', event)" onmouseleave="hideStockPopup()">
    <span class="stock-name">${esc(stock.Name || stock.Ticker)}</span>
    <span class="stock-code">${esc(stock.Ticker)}</span>
  </td>
  <td class="desc-cell">${esc(stock.Desc || '')}</td>
  <td><span class="sector-tag">${esc(stock.Sector || '—')}</span></td>
  <td class="score-col">
    <div class="score-line"><span class="score-num ${sc}">${score}</span>${_deltaBadge(stock)}</div>
    <div class="score-bar-wrap"><div class="score-bar-fill ${sc}" style="width:${barW}%"></div></div>
  </td>
  <td>
    ${_renderSignalHtml(stock.Signal, stock)}
    ${riskHtml}
  </td>
  <td class="right">${fmtPrice(stock.Price)}</td>
  <td class="right ${chgClass}">${chgSign}${chgPct}%</td>
  <td class="right">${rsi}</td>
  <td class="right" style="color:${stock.TargetUpside > 0 ? 'var(--success)' : 'var(--text-tertiary)'}" title="${stock.TargetSource ? '출처: ' + esc(stock.TargetSource) + (stock.TargetPrice ? ' · 목표가 ' + fmtPrice(stock.TargetPrice) : '') : '목표가 없음'}">${upside}</td>
  <td class="reason-cell">${reasonHtml}</td>
</tr>`;
}

// ── 회사 정보 팝업 ──────────────────────────────────────────────────────

function showStockPopup(ticker, ev) {
  const s = _stockMap[ticker];
  if (!s) return;
  const pop = document.getElementById('stock-popup');
  if (!pop) return;

  const name = esc(s.Name || ticker);
  const industry = esc(s.Industry || '');
  const info = esc(s.CompanyInfo || '');

  pop.innerHTML = `
    <div class="popup-header">
      <strong class="popup-name">${name}</strong>
      <span class="popup-ticker">${esc(ticker)}</span>
    </div>
    ${industry ? `<div class="popup-industry">${industry}</div>` : ''}
    ${info ? `<div class="popup-desc">${info}</div>` : ''}`;

  // 위치 계산 — 셀 아래에 표시, 화면 밖으로 나가지 않도록 조정
  const rect = ev.currentTarget.getBoundingClientRect();
  const scrollY = window.scrollY || document.documentElement.scrollTop;
  let left = rect.left;
  if (left + 340 > window.innerWidth) left = window.innerWidth - 350;
  if (left < 8) left = 8;
  pop.style.left = left + 'px';
  pop.style.top  = (rect.bottom + scrollY + 6) + 'px';
  pop.classList.add('visible');
}

function hideStockPopup() {
  const pop = document.getElementById('stock-popup');
  if (pop) pop.classList.remove('visible');
}

function _colCount() {
  const ths = document.querySelectorAll('.stock-table thead th');
  return ths.length || 11;
}

function setStockListMsg(msg) {
  const tbody = document.getElementById('stock-list');
  if (tbody) tbody.innerHTML = `<tr><td colspan="${_colCount()}" class="state-msg">${esc(msg)}</td></tr>`;
}

function setStatHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

// ── 검색 (클라이언트 필터) ───────────────────────────────────────────────

function initSearch() {
  const inp = document.getElementById('search-input');
  if (!inp) return;
  inp.addEventListener('input', () => {
    const q = inp.value.trim().toLowerCase();
    if (!q) {
      if (allStocks.length) renderStockTable(allStocks);
      return;
    }
    if (!allStocks.length) {
      setStockListMsg('먼저 섹터를 선택하거나 스캔을 실행해주세요.');
      return;
    }
    const filtered = allStocks.filter(s =>
      (s.Ticker || '').toLowerCase().includes(q) ||
      (s.Name   || '').toLowerCase().includes(q) ||
      (s.Sector || '').toLowerCase().includes(q)
    );
    renderStockTable(filtered);
  });
}

// ── 디테일 페이지 ────────────────────────────────────────────────────────

async function loadDetail(ticker) {
  const p = new URLSearchParams({ market: currentMarket, strategy: currentStrategy });
  try {
    const res = await fetch(`/api/ticker/${ticker}?${p}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    populateDetail(data);
  } catch (e) {
    console.error('loadDetail 실패:', e);
    setText('detail-name', '데이터를 불러올 수 없습니다');
  }
}

function populateDetail(d) {
  setText('detail-name',   d.Name   || d.Ticker || '—');
  setText('detail-ticker', d.Ticker || '—');
  setText('detail-sector', d.Sector || '—');
  setText('detail-rsi',    d.RSI != null ? `RSI ${fmt(d.RSI, 1)}` : '—');
  setText('detail-price',  d.Price != null ? fmtPrice(d.Price) : '—');
  setText('detail-target', d.TargetPrice ? fmtPrice(d.TargetPrice) : '—');

  const scoreEl = document.getElementById('detail-score');
  if (scoreEl) {
    const sc = scoreClass(d.TotalScore || 0);
    scoreEl.textContent = Math.round(d.TotalScore || 0);
    scoreEl.className   = `hero-score ${sc}`;
  }

  const sigEl = document.getElementById('detail-signal');
  if (sigEl) {
    const { base } = _splitSignal(d.Signal);
    sigEl.textContent = _trKo(base || '—');
    sigEl.style.color = signalColor(base);
  }

  if (Array.isArray(d.Breakdown)) renderBreakdown(d.Breakdown);
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

/* 보조지표 영문→한글 번역 */
const _KALMAN_KO = {'BUY_TREND':'매수 추세','SELL_TREND':'하락 추세 — 진입 회피','POSSIBLE_REVERSAL':'반전 가능','NEUTRAL':'관망','OVERHEATED':'과열 — 진입 주의','OVERSOLD':'과매도 — 매수 후보','STRONG_BUY':'강한 매수','STRONG_SELL':'강한 회피'};
const _MARKET_KO = {'STRONG_BULL':'강한 상승장','BULL':'상승장','SIDEWAYS (Leaning Bull)':'횡보(상승 우위)','SIDEWAYS':'횡보','BEAR':'하락장','STRONG_BEAR':'강한 하락장'};
function _auxTextKo(badge, text, st) {
  if (badge === 'MATH') {
    const hm = text.match(/Hurst\s+([\d.]+)/);
    const km = text.match(/Kalman\s+(\S+)/);
    const h = hm ? hm[1] : '—';
    const k = km ? (_KALMAN_KO[km[1]] || km[1].replace('SELL','진입 회피')) : '—';
    const hv = parseFloat(h);
    const hDesc = isNaN(hv) ? '' : hv > 0.7 ? '강한 추세' : hv > 0.5 ? '추세 지속' : hv > 0.4 ? '약한 추세' : '역추세(반전 가능)';
    const hTxt = hDesc ? `${h} (${hDesc})` : h;
    if (st === 'pass') return `추세 지속성 ${hTxt} · 칼만 ${k} — 신뢰도 높음`;
    if (st === 'warn') return `추세 지속성 ${hTxt} · 칼만 ${k} — 신뢰도 낮음`;
    return `추세 지속성 ${hTxt} · 칼만 ${k}`;
  }
  if (badge === 'M') {
    for (const [eng, ko] of Object.entries(_MARKET_KO)) {
      if (text.includes(eng)) return text.includes('Cap') ? `${ko} — 점수 상한 적용` : ko;
    }
  }
  if (badge === 'FS') {
    return text.replace('Fail-Safe', '안전장치').replace('EPS<0', 'EPS 적자');
  }
  if (badge === 'SG') {
    const mm = text.match(/×\s*([\d.]+)/);
    const cr = text.match(/\(([^)]+)\)/);
    return `슈퍼 성장 배율 ×${mm ? mm[1] : '?'}${cr ? ' (' + cr[1] + ')' : ''}`;
  }
  return text.replace('Bear Cap', '하락장 상한');
}

/* Breakdown 영문 레이블 → 한글 (label, 한줄 설명) */
const _LABEL_KO = {
  'EPS 가속도 (Current QE)':        ['EPS 가속도',       '분기 순이익 성장 가속 여부'],
  '연간실적 ROE 기준 (Annual EPS)': ['연간 ROE 실적',    '자기자본이익률 기준 충족 여부'],
  '신고가·피벗 돌파 (New Highs)':   ['신고가·피벗 돌파', '52주 최고가 및 패턴 돌파'],
  '거래량 확인 돌파 (Supply/Demand)':['거래량 확인 돌파', '기관 참여를 동반한 거래량 급증'],
  '주도주 판별 (Leader/Laggard)':   ['주도주 판별',      '시장 대비 상대강도 측정'],
  '기관 수급 (Institutional)':      ['기관 수급',        '기관 자금의 매수·매도 흐름'],
  '시장 방향 (Market Direction)':   ['시장 방향',        '전체 시장 추세와 방향성'],
  'Fama-French Factor':             ['가치·퀄리티 팩터', '저평가·고품질 종목 선별'],
  'Mean Reversion':                 ['평균 회귀',        'RSI·Z-Score 기반 반등/조정 가능성'],
  'Momentum (Carhart)':             ['모멘텀',           '12개월 수익률 기반 추세 지속력'],
  'Multi-Timeframe':                ['다중 시간대',      '단기·중기·장기 추세 종합'],
  'Drawdown Risk':                  ['낙폭 위험도',      '최근 최대 하락폭(MDD) 평가'],
  'Smart Money Flow':               ['스마트머니 흐름',  '기관 자금 흐름과 OBV 추세'],
  'Analyst Target':                 ['애널리스트 목표가','목표가 대비 상승 여력'],
  'Short Interest':                 ['공매도 비율',      '공매도 부담 수준 평가'],
  'Hurst Exponent':                 ['허스트 지수',      '추세 지속성과 방향 예측력'],
  'Kalman Filter':                  ['칼만 필터',        '노이즈 제거 후 추세 신호'],
  'Stat Arb Z-Score':               ['통계적 Z-Score',   '통계적 과매수/과매도 위치'],
  'Vol-Adjusted (DE Shaw)':         ['변동성 조정',      '변동성 대비 수익률 효율성'],
  '시장 심리 프록시':               ['시장 심리 추정',   '가격·거래량 기반 투자 심리'],
  'ORB 돌파':                       ['ORB 돌파',         '시가 범위 돌파 신호'],
  'NR7 변동성 압축':                ['NR7 압축',         '7일 최저 변동폭 수축'],
  '볼린저 반등':                    ['볼린저 반등',      '볼린저밴드 하단 반등 신호'],
};

const _CS_WHAT = {
  'C':         '분기 순이익 증가율 — 최근 분기 EPS가 전년 동기 대비 얼마나 성장했는지 측정합니다. 오닐 기준 25% 이상이 목표입니다.',
  'A':         '연간 ROE 기준 — 자기자본으로 얼마나 많은 이익을 내는지 측정합니다. 오닐 기준 17% 이상이 합격선입니다.',
  'N':         '신고가·피벗 돌파 — 52주 최고가 근접 여부와 컵앤핸들 패턴의 피벗 돌파를 측정합니다.',
  'S':         '거래량 수반 돌파 — 기관의 매수를 동반한 거래량 급증으로 진짜 돌파인지 확인합니다.',
  'L':         '시장 주도주 여부 — 시장 대비 상대강도(RS Rating)를 측정합니다. 80점 이상이 주도주 기준입니다.',
  'I':         '기관 자금 수급 — 스마트머니(기관·세력)의 매수/매도 압력을 자금 흐름 지표로 측정합니다.',
  'M':         '시장 방향 — 현재 전체 시장이 상승장(Bull)인지 하락장(Bear)인지 추세와 ADX로 측정합니다.',
  'Quant':     '퀀트 보조 전략 — Fama-French 팩터, 모멘텀, 평균회귀 등 통계 기반 전략 점수입니다.',
  'Math':      '수학적 시계열 분석 — 허스트 지수(추세 지속성), 칼만 필터(노이즈 제거), Z-Score(통계적 위치)를 활용합니다.',
  'Adj':       '변동성 조정 — DE Shaw 방식으로 변동성 대비 수익률 효율성을 평가해 최종 점수를 미세 조정합니다.',
  'Sentiment': '시장 심리 추정 — 뉴스 없이 가격·거래량만으로 투자 심리를 간접 측정합니다.',
  'Scalp':     '단타 시그널 — ORB 돌파, NR7 변동성 압축, 볼린저밴드 반등 등 단기 트레이딩 신호입니다.',
};

function _breakdownItemHtml(item) {
  const [label, score, desc] = item;

  // CAN SLIM 원칙 요약 — 구조화된 컬러 카드
  if (label.includes('CAN SLIM')) {
    const lines = (desc || '').split('\n').filter(Boolean);
    const main = [], aux = [];
    for (const line of lines) {
      let st = 'neutral';
      if (/[✅🔥🚀⭐🔔]/.test(line)) st = 'pass';
      else if (/[⛔📉🚫]/.test(line)) st = 'fail';
      else if (/⚠/.test(line)) st = 'warn';
      const bm = line.match(/^\[([^\]]+)\]\s*(.*)/);
      const lm = line.match(/^([CANSLI])\S*\s+(.*)/);
      const em = line.match(/^[⛔⭐]\s*(.*)/);
      if (bm) { aux.push({b: bm[1].replace(/[^\w]/g,''), t: bm[2], st}); }
      else if (lm) { main.push({b: lm[1], t: lm[2], st}); }
      else if (em) { const badge = line.startsWith('\u26d4') ? 'FS' : 'SG'; aux.push({b: badge, t: em[1], st}); }
      else { aux.push({b: '\u00b7', t: line, st}); }
    }
    let h = '<div class="cs-canslim-wrap">';
    h += `<div class="cs-canslim-hdr">${esc(label)}</div>`;
    for (const g of main) h += `<div class="cs-tag cs-tag-${g.st}"><span class="cs-tag-b">${esc(g.b)}</span><span class="cs-tag-t">${esc(_trKo(g.t))}</span></div>`;
    if (aux.length) {
      h += '<div class="cs-tag-sep">\ubcf4\uc870 \uc9c0\ud45c</div>';
      for (const g of aux) h += `<div class="cs-tag cs-tag-${g.st}"><span class="cs-tag-b cs-tag-b-aux">${esc(g.b)}</span><span class="cs-tag-t">${esc(_auxTextKo(g.b, g.t, g.st))}</span></div>`;
    }
    return h + '</div>';
  }

  const badgeMatch = label.match(/^\[([^\]]{1,12})\]/);
  if (!badgeMatch) {
    // 섹션 헤더 — 전체 너비 배너
    const descHtml = esc(desc || '').replace(/\n/g, '<br>');
    return `<div class="cs-section-banner">
  <div style="font-size:13px;font-weight:700;color:var(--brand);margin-bottom:4px;">${esc(label)}</div>
  <div style="font-size:12px;color:var(--text-secondary);line-height:1.6;">${descHtml}</div>
</div>`;
  }
  const badge    = badgeMatch[1];
  const cleanLbl = label.replace(/^\[[^\]]+\]\s*/, '');
  const sc       = scoreClass(score);
  const barW     = Math.min(100, Math.max(0, score));
  // 한글 레이블 + 한줄 설명
  const mapped    = _LABEL_KO[cleanLbl];
  const koLbl     = mapped ? mapped[0] : cleanLbl.replace(/\s*\([^)]*\)\s*/g, '');
  const koHint    = mapped ? mapped[1] : (_CS_WHAT[badge] || '').split('—')[0].trim();
  // desc에서 핵심 줄만 최대 2줄
  const briefDesc = (desc || '').split('\n').filter(Boolean).slice(0, 2).join(' · ');
  return `<div class="cs-card">
  <div class="cs-card-top">
    <div class="cs-badge">${esc(badge)}</div>
    <div class="cs-card-label">
      <div class="cs-label-en">${esc(koLbl)}</div>
      ${koHint ? `<div class="cs-label-concept">${esc(koHint)}</div>` : ''}
    </div>
  </div>
  <div class="cs-score-big ${sc}">${fmt(score, 1)}</div>
  <div class="cs-bar-wrap"><div class="cs-bar-fill ${sc}" style="width:${barW}%"></div></div>
  ${briefDesc ? `<div class="cs-desc-brief">${esc(_trKo(briefDesc))}</div>` : ''}
</div>`;
}

function renderBreakdown(items) {
  const list = document.getElementById('dp-breakdown-list');
  if (list) list.innerHTML = `<div class="cs-card-grid">${items.map(_breakdownItemHtml).join('')}</div>`;
}

// ── 디테일 드로어 ────────────────────────────────────────────────────────

async function openDetail(ticker) {
  const overlay = document.getElementById('detail-overlay');
  const panel   = document.getElementById('detail-panel');
  if (!overlay || !panel) { location.href = `/detail/${encodeURIComponent(ticker)}?market=${currentMarket}&strategy=${currentStrategy}`; return; }

  _clearPanelDetail();
  overlay.classList.add('visible');
  panel.classList.add('open');
  document.body.style.overflow = 'hidden';

  try {
    const p   = new URLSearchParams({ market: currentMarket, strategy: currentStrategy });
    const res = await fetch(`/api/ticker/${encodeURIComponent(ticker)}?${p}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    _populatePanelDetail(data);
  } catch (e) {
    console.error('openDetail 실패:', e);
    setText('dp-name', '데이터를 불러올 수 없습니다');
  }
}

function closeDetailBtn() {
  const overlay = document.getElementById('detail-overlay');
  const panel   = document.getElementById('detail-panel');
  if (!overlay || !panel) return;
  overlay.classList.remove('visible');
  panel.classList.remove('open');
  document.body.style.overflow = '';
}

function _clearPanelDetail() {
  const _ab = document.getElementById('dp-about-box');
  if (_ab) _ab.style.display = 'none';
  ['dp-name','dp-ticker','dp-sector','dp-about','dp-score','dp-signal',
   'dp-price','dp-day-chg','dp-target','dp-upside','dp-rsi','dp-conviction',
   'dp-axis-eps-val','dp-axis-roe-val','dp-axis-mom-val','dp-axis-dd-val'].forEach(id => setText(id, '…'));
  const loading = '<div style="padding:32px 16px;text-align:center;color:var(--text-tertiary);font-size:13px;">로딩 중...</div>';
  const bl = document.getElementById('dp-breakdown-list');
  if (bl) bl.innerHTML = loading;
  const tc = document.getElementById('dp-tech-content');
  if (tc) tc.innerHTML = loading;
  const fc = document.getElementById('dp-finance-content');
  if (fc) fc.innerHTML = loading;
}

function _populatePanelDetail(d) {
  setText('dp-name',    d.Name   || d.Ticker || '—');
  setText('dp-ticker',  d.Ticker || '—');
  setText('dp-sector',  d.Sector || '—');
  const aboutText = d.Desc || '';
  const aboutEl   = document.getElementById('dp-about');
  const aboutBox  = document.getElementById('dp-about-box');
  if (aboutEl)  aboutEl.textContent = aboutText;
  if (aboutBox) aboutBox.style.display = aboutText ? '' : 'none';
  setText('dp-price',   d.Price  != null ? fmtPrice(d.Price) : '—');
  setText('dp-target',  d.TargetPrice ? fmtPrice(d.TargetPrice) : '—');
  const tgtSrcEl = document.getElementById('dp-target-src');
  if (tgtSrcEl) {
    if (d.TargetPrice && d.TargetSource) {
      tgtSrcEl.textContent = d.TargetSource;
      tgtSrcEl.title = '목표가 출처: ' + d.TargetSource;
    } else {
      tgtSrcEl.textContent = '';
      tgtSrcEl.removeAttribute('title');
    }
  }
  setText('dp-rsi',     d.RSI    != null ? fmt(d.RSI, 1) : '—');
  setText('dp-conviction', _trKo(d.Conviction || '—'));

  const dayChg = d.DayChg || 0;
  const chgEl  = document.getElementById('dp-day-chg');
  if (chgEl) {
    const sign = dayChg > 0 ? '+' : '';
    chgEl.textContent = `${sign}${(dayChg * 100).toFixed(2)}%`;
    chgEl.className = 'dp-metric-val ' + (dayChg > 0 ? 'chg-up' : dayChg < 0 ? 'chg-down' : 'chg-flat');
  }

  const upsideEl = document.getElementById('dp-upside');
  if (upsideEl) {
    const u = d.TargetUpside;
    upsideEl.textContent = u != null ? (u >= 0 ? '+' : '') + fmt(u * 100, 1) + '%' : '—';
    upsideEl.style.color = u > 0 ? 'var(--success)' : u < 0 ? 'var(--destructive)' : 'var(--text-tertiary)';
  }

  const scoreEl = document.getElementById('dp-score');
  if (scoreEl) {
    scoreEl.textContent = Math.round(d.TotalScore || 0);
    scoreEl.className   = 'dp-score-num ' + scoreClass(d.TotalScore || 0);
  }

  const sigEl = document.getElementById('dp-signal');
  if (sigEl) {
    const { base } = _splitSignal(d.Signal);
    sigEl.textContent = _trKo(base || '—');
    sigEl.style.color      = signalColor(base);
    sigEl.style.background = signalBg(base);
  }

  // 4-axis 미니 지표
  const eps = d._EPSGrowth != null ? (d._EPSGrowth * 100).toFixed(1) + '%' : '—';
  const roe = d._ROE       != null ? (d._ROE       * 100).toFixed(1) + '%' : '—';
  const mom = d.Mom12M     != null ? (d.Mom12M     * 100).toFixed(1) + '%' : '—';
  const rsr = d.RSRating != null ? Math.round(d.RSRating).toString() : '—';
  setText('dp-axis-eps-val', eps);
  setText('dp-axis-roe-val', roe);
  setText('dp-axis-mom-val', mom);
  setText('dp-axis-rs-val',  rsr);

  // 진입 타이밍 카드
  _renderEntryCard(d);

  // 기술·재무 탭
  _renderTechTab(d);
  _renderFinanceTab(d);

  if (Array.isArray(d.Breakdown)) renderBreakdown(d.Breakdown);

  // CAN SLIM 탭으로 초기화
  switchDpTab('canslim');

  // 차트 자동 로드 (탭 제거되어 항상 표시)
  const tk = (document.getElementById('dp-ticker')?.textContent || '').trim();
  if (tk && tk !== '—' && tk !== '…' && _dpFourAxisLoadedFor !== tk) {
    _dpFourAxisLoadedFor = tk;
    loadDpFourAxis(tk);
  }
}

// ── 영어 → 한국어 번역 테이블 ────────────────────────────────────────────

const _KO_MAP = {
  // Conviction
  'HIGH': '높음', 'MID': '보통', 'LOW': '낮음',
  // Regime
  'BULL': '상승장', 'BEAR': '하락장', 'NEUTRAL': '관망', 'SIDEWAYS': '횡보',
  // Signal keywords
  'STRONG LEADER': '강력 리더', 'LEADER': '리더', 'WATCH': '관찰',
  'ACCUMULATE': '매집', 'HOLD': '진입 보류', 'SELL': '진입 회피',
  'AVOID': '회피', 'LAGGARD': '낙후', 'BREAKOUT': '돌파',
  'MOMENTUM': '모멘텀', 'CAUTION': '주의', 'BEAR MARKET': '하락장',
  // ORB/NR7/BB signals
  'BUY': '매수', 'NO SIGNAL': '신호 없음', 'PARTIAL': '부분',
  'OVERSOLD': '과매도', 'OVERBOUGHT': '과매수',
  'NR7 COMPRESSION': 'NR7 압축', 'SQUEEZE': '수축',
  'BUY_TREND': '매수 추세', 'SELL_TREND': '하락 추세',
  'POSSIBLE_REVERSAL': '반전 가능', 'RANGE': '횡보',
  'CONFIRMED': '확인', 'FAILED': '실패',
  // Breakdown desc 번역 (compound terms first)
  'STRONG_BUY': '강력 매수', 'STRONG_BULLISH': '강한 상승', 'STRONG_BEARISH': '강한 하락',
  'MILD_BULLISH': '약한 상승', 'MILD_BEARISH': '약한 하락',
  'STRONG_S_CONFIRMED': '강한 수급 확인', 'S_CONFIRMED': '수급 확인', 'S_WEAK': '수급 약함',
  'STRONG_DISTRIBUTION': '강한 분산', 'MILD_DISTRIBUTION': '약한 분산',
  'UNCONFIRMED_BREAKOUT': '미확인 돌파', 'NO_INTEREST': '관심 부족',
  'STRONG_TREND': '강한 추세', 'MEAN_REVERTING': '평균 회귀', 'RANDOM_WALK': '불규칙',
  'ORB_BREAKOUT': 'ORB 돌파', 'OVERHEATED': '과열',
  'MODERATE_BUY': '적정 매수', 'SLIGHT_UPSIDE': '소폭 상승 여력',
  'SLIGHT_OVERVALUED': '소폭 고평가', 'AT_TARGET': '목표가 도달',
  'ABOVE_STRONG': '강한 상회', 'BELOW_WEAK': '약한 하회',
  'BULLISH': '상승', 'BEARISH': '하락', 'MODERATE': '보통',
  'ACCUMULATION': '매집', 'DISTRIBUTION': '분산',
  'ABOVE': '상회', 'BELOW': '하회', 'TRENDING': '추세 진행',
  'OVERVALUED': '고평가', 'EXTREME': '극심',
  'INFLOW': '유입', 'OUTFLOW': '유출', 'NONE': '없음',
};

function _trKo(str) {
  if (!str) return str;
  let s = String(str);
  // 정확히 일치하는 키부터 (대소문자 무시)
  const upper = s.toUpperCase().trim();
  if (_KO_MAP[upper]) return s.replace(new RegExp(upper, 'i'), _KO_MAP[upper]);
  // 부분 치환
  s = Object.entries(_KO_MAP).reduce((acc, [en, ko]) => {
    return acc.replace(new RegExp('\\b' + en + '\\b', 'gi'), ko);
  }, s);
  // 동일 단어 중복 제거 ("관망 - 관망" → "관망")
  s = s.replace(/(\S+)(\s*[-·/|]\s*)\1\b/g, '$1');
  return s;
}

function _rsiLabel(v)  { if (!v) return ''; return v > 70 ? ' · 과매수' : v < 30 ? ' · 과매도' : v > 60 ? ' · 강세' : v < 40 ? ' · 약세' : ' · 관망'; }
function _adxLabel(v)  { if (!v) return ''; return v > 40 ? ' · 강한 추세' : v > 25 ? ' · 추세 형성' : ' · 추세 약함'; }
function _rsLabel(v)   { if (v == null) return ''; return v >= 80 ? ' · 섹터 리더' : v >= 60 ? ' · 평균 이상' : v < 40 ? ' · 하위권' : ''; }
function _roeLbl(v)    { if (!v) return ''; return v > 0.20 ? ' · 우수' : v > 0.15 ? ' · 양호' : v > 0 ? ' · 보통' : ' · 미흡'; }
function _epsLbl(v)    { if (!v) return ''; return v > 0.25 ? ' · 고성장' : v > 0.10 ? ' · 성장' : v > 0 ? ' · 완만' : ' · 감소'; }

function _indicatorRowHtml(label, val, sub, color) {
  const col = color || 'var(--text-primary)';
  const bc = col === 'var(--success)' ? ' ind-pos' : col === 'var(--destructive)' ? ' ind-neg' : col === 'var(--info)' ? ' ind-info' : '';
  return `
<div class="ind-row${bc}">
  <div>
    <div class="ind-label">${esc(label)}</div>
    ${sub ? `<div class="ind-sub">${esc(sub)}</div>` : ''}
  </div>
  <div class="ind-val" style="color:${col};">${esc(val)}</div>
</div>`;
}

function _renderTechTab(d) {
  const el = document.getElementById('dp-tech-content');
  if (!el) return;

  const rsiVal  = d.RSI    != null ? fmt(d.RSI, 1) + _rsiLabel(d.RSI)   : '—';
  const rsiCol  = d.RSI > 70 ? 'var(--destructive)' : d.RSI < 30 ? 'var(--info)' : 'var(--text-primary)';
  const adxRaw  = d._ADX != null ? fmt(d._ADX, 1) + _adxLabel(d._ADX) : '—';
  const adxCol  = d._ADX > 25 ? 'var(--success)' : 'var(--text-tertiary)';
  const rsRaw   = d.RSRating != null ? String(d.RSRating) + _rsLabel(d.RSRating) : '—';
  const rsCol   = d.RSRating >= 80 ? 'var(--success)' : d.RSRating < 40 ? 'var(--destructive)' : 'var(--text-primary)';
  const vwapRaw = d.VWAPDistance != null ? (d.VWAPDistance >= 0 ? '+' : '') + fmt(d.VWAPDistance*100,1)+'%'
                  + (d.VWAPDistance > 0.03 ? ' · VWAP 위' : d.VWAPDistance < -0.03 ? ' · VWAP 아래' : ' · VWAP 근접') : '—';
  const volRaw  = d.VolRatio != null ? fmt(d.VolRatio, 2)+'x'
                  + (d.VolRatio > 2 ? ' · 급증' : d.VolRatio > 1.3 ? ' · 증가' : d.VolRatio < 0.7 ? ' · 감소' : ' · 보통') : '—';

  const rows = [
    ['RSI (14)',    rsiVal,  '70↑ 과매수(조정 주의) · 30↓ 과매도(매수 기회)', rsiCol],
    ['ADX',        adxRaw,  '25↑ 추세 존재 · 40↑ 강한 추세 · 25↓ 횡보',     adxCol],
    ['ATR%',       d.ATRPercent != null ? fmt(d.ATRPercent*100,2)+'%' : '—', '높을수록 변동성 큼 — 위험과 기회 동시', null],
    ['VWAP 거리',  vwapRaw, '양수=평균가 위(강세) · 음수=아래(약세)',         d.VWAPDistance > 0 ? 'var(--success)' : 'var(--destructive)'],
    ['RS 등급',    rsRaw,   '80↑ 시장 주도주 · 40↓ 부진주',                  rsCol],
    ['12M 수익률', d.Mom12M != null ? (d.Mom12M >= 0 ? '+' : '') + fmt(d.Mom12M*100,1)+'%' : '—',
     '1년간 주가 등락 — 양수면 상승 추세', d.Mom12M > 0 ? 'var(--success)' : 'var(--destructive)'],
    ['3M 수익률',  d._Mom3M != null ? (d._Mom3M >= 0 ? '+' : '') + fmt(d._Mom3M,1)+'%' : '—',
     '3개월간 주가 등락 — 단기 추세 확인', d._Mom3M > 0 ? 'var(--success)' : 'var(--destructive)'],
    ['거래량 비율',volRaw,  '1↑ 평소보다 활발 · 2↑ 기관 참여 가능성',        d.VolRatio > 1.5 ? 'var(--success)' : null],
    ['ORB 신호',   _trKo(d.ORBSignal  || '—'), '시초가 범위 돌파 시 매수 신호',     null],
    ['NR7 압축',   _trKo(d.NR7Signal  || '—'), '변동폭 수축 후 큰 움직임 대비',     null],
    ['볼린저밴드', _trKo(d.BBSignal   || '—'), '하단 반등=매수 기회 · 상단=과열 주의', null],
    ['확신도',     _trKo(d.Conviction || '—'), '높음=팩터 방향 일치 · 낮음=신호 혼재', null],
  ];

  el.innerHTML = rows.map(([l, v, s, c]) => _indicatorRowHtml(l, v, s, c)).join('');
}

function _renderFinanceTab(d) {
  const el = document.getElementById('dp-finance-content');
  if (!el) return;

  // 재무 데이터가 전부 0이면 데이터 없음 메시지
  const hasFinance = d._PER || d._PBR || d._ROE || d._MarketCap;
  if (!hasFinance) {
    el.innerHTML = `<div style="padding:24px 16px;text-align:center;color:var(--text-tertiary);font-size:13px;line-height:1.8;">
      <div style="font-size:22px;margin-bottom:8px;">📊</div>
      Yahoo Finance에서 이 종목의 재무 데이터를<br>제공하지 않아요.<br>
      <span style="font-size:11px;margin-top:4px;display:block;">한국 종목은 네이버 증권을 참고해 주세요.</span>
    </div>`;
    return;
  }

  const roeRaw = d._ROE ? fmt(d._ROE * 100, 1) + '%' + _roeLbl(d._ROE) : '—';
  const epsRaw = d._EPSGrowth != null ? (d._EPSGrowth >= 0 ? '+' : '') + fmt(d._EPSGrowth*100,1)+'%' + _epsLbl(d._EPSGrowth) : '—';
  const perLbl = d._PER ? (d._PER < 15 ? ' · 저평가 가능' : d._PER > 40 ? ' · 고평가 주의' : '') : '';
  const pbrLbl = d._PBR ? (d._PBR < 1 ? ' · 자산 대비 저평가' : d._PBR > 5 ? ' · 고평가' : '') : '';
  const dbtLbl = d._DebtRatio ? (d._DebtRatio > 200 ? ' · 위험' : d._DebtRatio > 100 ? ' · 주의' : ' · 안정') : '';
  const omLbl  = d._OperatingMargin ? (d._OperatingMargin > 0.20 ? ' · 우수' : d._OperatingMargin > 0.10 ? ' · 양호' : d._OperatingMargin > 0 ? ' · 보통' : ' · 손실') : '';

  const rows = [
    ['PER',       d._PER   ? fmt(d._PER, 1) + perLbl  : '—', '주가÷순이익 · 15↓ 저평가 · 40↑ 고평가',    d._PER && d._PER < 15 ? 'var(--success)' : d._PER > 40 ? 'var(--destructive)' : null],
    ['PBR',       d._PBR   ? fmt(d._PBR, 2) + pbrLbl  : '—', '주가÷순자산 · 1↓ 자산 대비 저렴',           null],
    ['ROE',       roeRaw,                                      '자기자본이익률 · 17%↑ 오닐 기준 합격',     d._ROE > 0.15 ? 'var(--success)' : null],
    ['EPS 성장률',epsRaw,                                      '분기 순이익 전년비 · 25%↑ 성장주 기준',    d._EPSGrowth > 0 ? 'var(--success)' : 'var(--destructive)'],
    ['영업이익률',d._OperatingMargin ? fmt(d._OperatingMargin*100,1)+'%' + omLbl : '—', '매출 대비 영업이익 · 20%↑ 우수',  null],
    ['부채비율',  d._DebtRatio ? fmt(d._DebtRatio, 1)+'%' + dbtLbl : '—', '100%↓ 양호 · 200%↑ 위험', d._DebtRatio > 150 ? 'var(--destructive)' : d._DebtRatio < 50 ? 'var(--success)' : null],
    ['시가총액',  d._MarketCap ? _fmtCap(d._MarketCap) : '—',          '기업 규모 — 클수록 안정적',         null],
    ['밸류 팩터', d.ValueScore   != null ? fmt(d.ValueScore, 1) + '점' : '—', '가치·저평가 매력도 — 양수=저평가', null],
    ['퀄리티 팩터',d.QualityScore!= null ? fmt(d.QualityScore,1) + '점': '—', '수익성·안정성 종합 — 높을수록 우량',    null],
  ];

  el.innerHTML = rows.map(([l, v, s, c]) => _indicatorRowHtml(l, v, s, c)).join('');
}

function _fmtCap(v) {
  if (!v) return '—';
  if (v >= 1e12) return (v/1e12).toFixed(1) + 'T';
  if (v >= 1e9)  return (v/1e9).toFixed(1)  + 'B';
  if (v >= 1e6)  return (v/1e6).toFixed(1)  + 'M';
  return String(v);
}

let _dpFourAxisLoadedFor = null;

function switchDpTab(tabId) {
  document.querySelectorAll('.dp-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  document.querySelectorAll('.dp-tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === `dp-tab-${tabId}`);
  });
}

async function loadDpFourAxis(ticker) {
  const loading = document.getElementById('dp-fouraxis-loading');
  const errDiv  = document.getElementById('dp-fouraxis-error');
  const header  = document.getElementById('dp-fouraxis-header');
  const chartW  = document.getElementById('dp-fouraxis-chart-wrap');
  const obsDiv  = document.getElementById('dp-fouraxis-obs');
  if (!loading) return;

  header.style.display = 'none';
  chartW.style.display = 'none';
  obsDiv.style.display = 'none';
  errDiv.style.display = 'none';
  loading.style.display = 'block';

  try {
    const p   = new URLSearchParams({ market: currentMarket });
    const res = await fetch(`/api/four_axis/${encodeURIComponent(ticker)}?${p}`);
    const d   = await res.json();
    if (d.error) throw new Error(d.error);

    document.getElementById('dp-fouraxis-chart').src = 'data:image/png;base64,' + d.chart;
    chartW.style.display = 'block';

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('dp-fa-phase', d.phase || '');
    set('dp-fa-stars', '★'.repeat(d.signal_stars || 0) + '☆'.repeat(5 - (d.signal_stars || 0)));
    set('dp-fa-haiku', d.haiku || '');
    set('dp-fa-trend-score',   d.trend?.score    ?? '-');
    set('dp-fa-trend-verdict', d.trend?.verdict  ?? '');
    set('dp-fa-mom-score',     d.momentum?.score ?? '-');
    set('dp-fa-mom-verdict',   d.momentum?.verdict ?? '');
    set('dp-fa-vol-score',     d.volatility?.score ?? '-');
    set('dp-fa-vol-verdict',   d.volatility?.verdict ?? '');
    set('dp-fa-volm-score',    d.volume?.score   ?? '-');
    set('dp-fa-volm-verdict',  d.volume?.verdict ?? '');
    header.style.display = 'block';

    const obs = d.key_observation || d.structured_analysis || '';
    if (obs) {
      document.getElementById('dp-fa-observation').textContent = obs;
      obsDiv.style.display = 'block';
    }
  } catch (e) {
    _dpFourAxisLoadedFor = null;
    errDiv.textContent = '4축 분석 로드 실패: ' + e.message;
    errDiv.style.display = 'block';
  } finally {
    loading.style.display = 'none';
  }
}

// ── 탭 전환 (detail.html onclick) ────────────────────────────────────────

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const active = btn.getAttribute('aria-controls') === `tab-${tabId}`;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === `tab-${tabId}`);
  });
}

async function loadFourAxis(ticker) {
  const loading = document.getElementById('fouraxis-loading');
  const errDiv  = document.getElementById('fouraxis-error');
  const chartW  = document.getElementById('fouraxis-chart-wrap');
  if (!loading) return;

  loading.style.display = 'block';
  errDiv.style.display  = 'none';

  try {
    const p   = new URLSearchParams({ market: currentMarket });
    const res = await fetch(`/api/four_axis/${ticker}?${p}`);
    const d   = await res.json();
    if (d.error) throw new Error(d.error);

    document.getElementById('fouraxis-chart').src = 'data:image/png;base64,' + d.chart;
    chartW.style.display = 'block';
  } catch (e) {
    errDiv.textContent = '차트 로드 실패: ' + e.message;
    errDiv.style.display = 'block';
  } finally {
    loading.style.display = 'none';
  }
}

if (typeof TICKER !== 'undefined' && TICKER) {
  document.addEventListener('DOMContentLoaded', () => loadFourAxis(TICKER));
}

// ── 관심 종목 토글 ───────────────────────────────────────────────────────

function toggleBookmark(btn) {
  const icon = document.getElementById('bookmarkIcon');
  if (!icon) return;
  const filled = icon.getAttribute('fill') !== 'none';
  icon.setAttribute('fill',   filled ? 'none' : '#3182F6');
  icon.setAttribute('stroke', '#3182F6');
}

// ── TopReason 태그 렌더링 ────────────────────────────────────────────

function _renderReasonTags(topReason) {
  if (!topReason || topReason === '-') return '<span style="color:var(--text-tertiary)">—</span>';
  const parts = topReason.split(' · ').slice(0, 4);
  return parts.map(p => {
    const neg = /⛔|과열|AVOID|SELL|적자/.test(p);
    const pos = /신고가|돌파|주도주|EPS|ROE|과매도/.test(p);
    const cls = neg ? ' negative' : pos ? ' positive' : '';
    return `<span class="reason-tag${cls}">${esc(p)}</span>`;
  }).join('');
}

// ── 테이블 정렬 ─────────────────────────────────────────────────────

function initFilterChips() {
  document.querySelectorAll('#filter-chips .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const f = chip.dataset.filter || 'all';
      if (_currentFilter === f) return;
      _currentFilter = f;
      document.querySelectorAll('#filter-chips .chip').forEach(c => c.classList.toggle('active', c === chip));
      if (allStocks.length) _refreshFilteredView();
    });
  });
}

function initSort() {
  // 초기 정렬 화살표 표시 (기본: Scores.BALANCED desc)
  document.querySelectorAll('.stock-table th.sortable').forEach(th => {
    if (th.dataset.sort === _sortKey) {
      th.classList.add(_sortDir === 1 ? 'asc' : 'desc');
    }
  });
  document.querySelectorAll('.stock-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (_sortKey === key) {
        _sortDir = _sortDir === -1 ? 1 : _sortDir === 1 ? 0 : -1;
      } else {
        _sortKey = key;
        _sortDir = -1; // 기본 내림차순
      }
      // 화살표 UI 갱신
      document.querySelectorAll('.stock-table th.sortable').forEach(h => {
        h.classList.remove('asc', 'desc');
      });
      if (_sortDir === 1)  th.classList.add('asc');
      if (_sortDir === -1) th.classList.add('desc');

      if (_sortDir === 0 || !allStocks.length) {
        if (allStocks.length) renderStockTable(allStocks);
        return;
      }
      const sorted = [...allStocks].sort((a, b) => {
        const va = _getByPath(a, key); const vb = _getByPath(b, key);
        const aa = va == null ? -Infinity : va;
        const bb = vb == null ? -Infinity : vb;
        return _sortDir * (aa > bb ? 1 : aa < bb ? -1 : 0);
      });
      renderStockTable(sorted);
    });
  });
}

// ── CSV 내보내기 ─────────────────────────────────────────────────────

function exportCSV() {
  if (!allStocks.length) {
    alert('내보낼 데이터가 없습니다. 먼저 스캔을 실행해주세요.');
    return;
  }
  const cols = [
    ['Ticker','티커'], ['Name','종목명'], ['Sector','섹터'], ['TotalScore','점수'],
    ['Signal','시그널'], ['Price','현재가'], ['DayChg','등락률'],
    ['RSI','RSI'], ['TargetPrice','목표가'], ['TargetSource','목표가출처'], ['TargetUpside','상승여력'],
    ['TargetView','컨센서스'], ['Conviction','확신도'], ['VolRatio','거래량비율'],
    ['TopReason','핵심이유'], ['MomentumScore','모멘텀'], ['ValueScore','밸류'],
    ['QualityScore','퀄리티'], ['RSRating','RS등급'],
    ['Industry','업종'], ['Desc','설명'],
  ];
  const header = cols.map(c => c[1]).join(',');
  const rows = allStocks.map(s =>
    cols.map(([k]) => {
      let v = s[k] ?? '';
      if (k === 'DayChg' || k === 'TargetUpside')
        v = v ? (v * 100).toFixed(2) + '%' : '';
      v = String(v).replace(/"/g, '""');
      if (String(v).includes(',') || String(v).includes('"') || String(v).includes('\n'))
        v = `"${v}"`;
      return v;
    }).join(',')
  );
  const csv = '\uFEFF' + header + '\n' + rows.join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  const date = new Date().toISOString().slice(0, 10);
  a.download = `검색기_${currentMarket}_${currentStrategy}_${date}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── 초기화 ───────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // URL 파라미터에서 market/strategy 읽기
  const sp = new URLSearchParams(window.location.search);
  if (sp.has('market'))   currentMarket   = sp.get('market');
  if (sp.has('strategy')) currentStrategy = sp.get('strategy');

  // 오늘 날짜 표시
  const dateEl = document.getElementById('topbar-date');
  if (dateEl) {
    dateEl.textContent = new Date().toLocaleDateString('ko-KR', {
      year: 'numeric', month: '2-digit', day: '2-digit'
    });
  }

  // 시장 셀렉터 동기화
  const mSel = document.getElementById('market-select');
  if (mSel) mSel.value = currentMarket;
  const sSel = document.getElementById('strategy-select');
  if (sSel) sSel.value = currentStrategy;

  // ESC로 드로어 닫기
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetailBtn(); });

  if (typeof TICKER !== 'undefined' && TICKER) {
    // ── 디테일 페이지
    loadDetail(TICKER);
  } else {
    // ── 스캐너 페이지
    loadWatchlist();
    initFilterChips();
    initSearch();
    initSort();
    document.getElementById('btn-scan')?.addEventListener('click', runScan);
    loadSectors();
  }
});
