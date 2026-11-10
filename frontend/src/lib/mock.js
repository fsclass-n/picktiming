// 데모 모드 목업 API: 실제 백엔드(/api/v1)와 같은 요청·응답 형식을 브라우저 안에서 흉내 낸다.
// 가격 이력은 상품 ID를 시드로 한 의사난수로 생성하므로 새로고침해도 같은 값이 나온다.

const DAY = 86400000;
export const PASSWORD_RULE = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9\s]).{8,72}$/;
const AI_DAILY_LIMIT = 20;
const LS = { watch: 'pt_mock_watchlist', alertsRead: 'pt_mock_alerts_read', custom: 'pt_mock_custom', quota: 'pt_mock_quota', users: 'pt_mock_users' };

const MALLS = [
  { id: 1, name: '쇼핑몰 A', offset: 0, ship: () => 0 },
  { id: 2, name: '쇼핑몰 B', offset: -0.016, ship: () => 3000 },
  { id: 3, name: '쇼핑몰 C', offset: 0.035, ship: (p) => (p >= 30000 ? 0 : 2500) },
];

const PRODUCTS = [
  { id: 1, name: '무선 이어폰 X2', brand: 'SoundOne', model_no: 'X2-ANC', category: '디지털', base: 139000, days: 120, phase: 'sale', spec: '커널형 / 블루투스 5.3 / 액티브노이즈캔슬링 / 최대재생: 30시간 / 무게: 5g' },
  { id: 2, name: '노이즈캔슬링 헤드폰 H7', brand: 'SoundOne', model_no: 'H7', category: '디지털', base: 329000, days: 120, phase: 'before', spec: '오버이어 / 블루투스 5.3 / 액티브노이즈캔슬링 / 최대재생: 40시간 / 무게: 250g' },
  { id: 3, name: '14인치 노트북 Air', brand: 'Bitbook', model_no: 'BA14-2026', category: '디지털', base: 1190000, days: 120 },
  { id: 4, name: '스마트워치 S5', brand: 'Tickr', model_no: 'S5-44', category: '디지털', base: 259000, days: 21 },
  { id: 5, name: '로봇청소기 R9', brand: 'CleanBot', model_no: 'R9', category: '가전', base: 489000, days: 120 },
  { id: 6, name: '에어프라이어 5.5L', brand: 'Kitchy', model_no: 'AF55', category: '가전', base: 99000, days: 120, phase: 'sale' },
  { id: 7, name: '무선 청소기 V8', brand: 'CleanBot', model_no: 'V8', category: '가전', base: 359000, days: 120, phase: 'before' },
  { id: 8, name: '생수 2L × 12', brand: '맑은샘', model_no: 'W2L12', category: '생필품', base: 8900, days: 120 },
  { id: 9, name: '세탁세제 3L', brand: '하얀빨래', model_no: 'LD3L', category: '생필품', base: 15900, days: 120, phase: 'sale' },
  { id: 10, name: '화장지 30롤', brand: '부드러움', model_no: 'TP30', category: '생필품', base: 21900, days: 120 },
  { id: 11, name: '분유 800g × 3', brand: '튼튼', model_no: 'MF800-3', category: '유아', base: 89000, days: 120 },
  { id: 12, name: '기저귀 대형 4팩', brand: '뽀송', model_no: 'DP-L4', category: '유아', base: 72000, days: 120, phase: 'before' },
];

const VERDICT = { BUY_NOW: '지금 구매 추천', WAIT_A_BIT: '조금 더 지켜보기', WAIT: '기다리기 권장', HOLD: '판단 보류' };
const CAUTION = '가격 예측은 과거 데이터 기반 참고 정보이며 실제 가격과 다를 수 있습니다.';

// ------------------------------------------------------------------ 유틸
function mulberry32(seed) {
  return () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const load = (k, d) => JSON.parse(localStorage.getItem(k) || JSON.stringify(d));
const save = (k, v) => localStorage.setItem(k, JSON.stringify(v));
const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const won = (n) => `${Math.round(n).toLocaleString('ko-KR')}원`;
const roundPrice = (v, base) => (base >= 100000 ? Math.round(v / 100) * 100 : Math.round(v / 10) * 10);
const ok = (body, status = 200) => ({ status, body });
const fail = (status, code, message) => ({ status, body: { code, message } });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sigmoid = (x) => 1 / (1 + Math.exp(-x));

function allProducts() { return [...PRODUCTS, ...load(LS.custom, [])]; }
function findProduct(id) { return allProducts().find((p) => p.id === Number(id)); }
// 데모 모드 상품 사진: 가상 상품이라 실제 사진이 없어 Unsplash 참고 이미지를 쓴다(화면에 "참고 이미지 · Unsplash"로 표시)
const DEMO_PHOTOS = [[/이어폰/, 'photo-1606220945770-b5b6c2c55bf1'], [/헤드폰/, 'photo-1505740420928-5e560c06d30e'],
  [/노트북/, 'photo-1496181133206-80ce9b88a853'], [/워치/, 'photo-1523275335684-37898b6baf30'], [/생수/, 'photo-1602143407151-7111542de6e8']];
const CATEGORY_PHOTOS = { 디지털: 'photo-1505740420928-5e560c06d30e', 가전: 'photo-1556911220-bff31c812dba', 생필품: 'photo-1542838132-92c53300491e',
  패션: 'photo-1542291026-7eec264c27ff', 유아: 'photo-1515488042361-ee00e0ddd4e4' };
function demoPhoto({ name = '', category }) {
  const id = (DEMO_PHOTOS.find(([re]) => re.test(name)) || [])[1] || CATEGORY_PHOTOS[category] || CATEGORY_PHOTOS.디지털;
  return `https://images.unsplash.com/${id}?auto=format&fit=crop&w=700&q=80`;
}
const publicProduct = (p) => ({ id: p.id, name: p.name, brand: p.brand, model_no: p.model_no, category: p.category, image_url: demoPhoto(p) });

// ------------------------------------------------------------------ 가격 이력 생성
const seriesCache = new Map();
function series(p) {
  if (seriesCache.has(p.id)) return seriesCache.get(p.id);
  const rnd = mulberry32(p.id * 9973 + 17);
  const days = p.days || 0;
  const period = 24 + Math.floor(rnd() * 10);
  let phase = Math.floor(rnd() * period);
  if (p.phase === 'sale') phase = (period - ((days - 2) % period)) % period;       // 최근 2일 할인 중
  if (p.phase === 'before') phase = (period - ((days + 2) % period)) % period;    // 2~3일 뒤 할인 예상
  const trend = (rnd() - 0.45) * 0.1;
  const t0 = today().getTime();
  const rows = [];
  let drift = 0;
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(t0 - i * DAY);
    const idx = days - 1 - i;
    drift = drift * 0.85 + (rnd() - 0.5) * 0.012;
    const onSale = (idx + phase) % period < 4;
    const f = 1 + trend * (idx / Math.max(days - 1, 1)) + drift + (onSale ? -0.1 - rnd() * 0.04 : 0) + (d.getDate() >= 26 ? -0.015 : 0);
    const malls = MALLS.map((m) => {
      const price = roundPrice(p.base * (f + m.offset + (rnd() - 0.5) * 0.012), p.base);
      const shipping_fee = m.ship(price);
      const in_stock = !(p.id === 7 && m.id === 3 && i < 2);
      return { mall_id: m.id, price, shipping_fee, total_price: price + shipping_fee, in_stock };
    });
    rows.push({ date: iso(d), malls });
  }
  seriesCache.set(p.id, rows);
  return rows;
}

const lowestOf = (row) => Math.min(...row.malls.filter((m) => m.in_stock).map((m) => m.total_price));

// ------------------------------------------------------------------ 적기 판정 (백엔드 규칙 기반 대체 로직과 동일한 개념)
function analyze(p) {
  const rows = series(p);
  const s = rows.map(lowestOf);
  const n = s.length;
  const base = { product_id: p.id, history_days: n, model_version: 'demo-heuristic' };
  if (n === 0) return { ...base, current_price: null, label: 'HOLD', score: null, prob_drop_7d: null, percentile_90d: null };
  const cur = s[n - 1];
  const w = s.slice(-90);
  const min90 = Math.min(...w);
  const avg90 = w.reduce((a, b) => a + b, 0) / w.length;
  const minIdx = n - w.length + w.indexOf(min90);
  if (n < 30) return { ...base, current_price: cur, min_90d: min90, avg_90d: Math.round(avg90), label: 'HOLD', score: null, prob_drop_7d: null, percentile_90d: null };
  const percentile = w.filter((v) => v < cur).length / (w.length - 1);
  const last30 = s.slice(-30);
  const mean30 = last30.reduce((a, b) => a + b, 0) / 30;
  const xm = 14.5;
  let num = 0; let den = 0;
  last30.forEach((v, i) => { num += (i - xm) * (v - mean30); den += (i - xm) ** 2; });
  const slope = (num / den / mean30) * 100;
  let sinceDrop = n;
  for (let i = n - 1; i >= 14; i--) {
    if (s[i] <= 0.92 * Math.max(...s.slice(i - 14, i))) { sinceDrop = n - 1 - i; break; }
  }
  const monthEnd = new Date().getDate() >= 26;
  const logit = -1.0 + 4.0 * (percentile - 0.35) + (sinceDrop > 20 ? 0.9 : -0.3) + (slope > 0.05 ? 0.4 : 0) + (monthEnd ? 0.2 : 0);
  const prob = Math.min(0.95, Math.max(0.03, sigmoid(logit)));
  const score = Math.round((1 - prob) * 70 + (1 - percentile) * 30);
  const label = score >= 70 ? 'BUY_NOW' : score >= 40 ? 'WAIT_A_BIT' : 'WAIT';
  const drops = [];
  for (let i = 14; i < n; i++) if (s[i] <= 0.92 * Math.max(...s.slice(i - 14, i)) && (!drops.length || i - drops[drops.length - 1] > 7)) drops.push(i);
  const cycle = drops.length > 1 ? Math.round((drops[drops.length - 1] - drops[0]) / (drops.length - 1)) : null;
  return {
    ...base, current_price: cur, min_90d: min90, min_90d_date: rows[minIdx].date, avg_90d: Math.round(avg90),
    percentile_90d: Number(percentile.toFixed(3)), prob_drop_7d: Number(prob.toFixed(3)), score, label,
    trend_30d_pct: Number(slope.toFixed(3)), days_since_drop: sinceDrop, discount_cycle_days: cycle,
  };
}

function advice(a) {
  if (a.label === 'HOLD') {
    return { verdict: VERDICT.HOLD, summary: `가격 이력이 ${a.history_days}일로 30일 미만이라 구매 적기를 판단하기 어렵습니다.`,
      reasons: ['가격 이력 30일 이상부터 판정', '목표가를 설정하면 도달 시 알려 드립니다'], caution: CAUTION };
  }
  const gap = ((a.current_price / a.min_90d - 1) * 100).toFixed(1);
  const trend = a.trend_30d_pct > 0.05 ? '최근 30일 가격이 오르는 추세' : a.trend_30d_pct < -0.05 ? '최근 30일 가격이 내리는 추세' : '최근 30일 가격 변동이 작음';
  const cycle = a.discount_cycle_days ? `할인 주기 약 ${a.discount_cycle_days}일, 마지막 할인 후 ${a.days_since_drop}일 경과` : '뚜렷한 할인 주기 없음';
  return {
    verdict: VERDICT[a.label],
    summary: `현재 최저 실구매가 ${won(a.current_price)}은 최근 90일 가격 중 하위 ${Math.round(a.percentile_90d * 100)}% 수준입니다. 과거 패턴상 7일 안에 5% 이상 더 내려갈 가능성은 ${Math.round(a.prob_drop_7d * 100)}%입니다.`,
    reasons: [`90일 최저가 ${won(a.min_90d)}과의 차이 ${gap}%`, trend, cycle],
    caution: CAUTION,
  };
}

function chatAnswer(p, a, question) {
  const q = question.replace(/\s/g, '');
  const cheapest = compare(p).items.find((i) => i.is_lowest);
  if (a.label === 'HOLD' && /기다|싸질|다음주|언제/.test(q)) return `가격 이력이 ${a.history_days}일뿐이라 앞으로의 가격 변화를 판단하기 어렵습니다. 목표가 알림을 설정해 두시는 것을 권합니다.`;
  if (/기다|싸질|다음주|내려/.test(q)) return `과거 패턴상 7일 안에 5% 이상 더 내려갈 가능성은 ${Math.round(a.prob_drop_7d * 100)}%입니다. 현재 판정은 '${VERDICT[a.label]}'이며, 지금 가격은 최근 90일 중 하위 ${Math.round(a.percentile_90d * 100)}% 수준입니다.`;
  if (/최저|역대|제일싼/.test(q)) return `최근 90일 최저 실구매가는 ${won(a.min_90d)}(${a.min_90d_date})이고, 현재는 ${won(a.current_price)}입니다.`;
  if (/언제|주기|할인/.test(q)) return a.discount_cycle_days ? `과거 데이터에서 할인은 약 ${a.discount_cycle_days}일 간격으로 나타났고, 마지막 할인 이후 ${a.days_since_drop}일이 지났습니다.` : '제공된 가격 이력에서는 뚜렷한 할인 주기를 찾지 못했습니다.';
  if (/어디|쇼핑몰|몰/.test(q) && cheapest) return `지금은 ${cheapest.mall}의 실구매가가 ${won(cheapest.total_price)}(배송비 포함)으로 가장 저렴합니다.`;
  return '제공된 가격 데이터로는 답하기 어려운 질문입니다. 가격 추이나 구매 시점에 대해 질문해 주세요.';
}

// 참가격(오프라인 판매점 조사가) 시연값: 생필품만, 조사일은 2주 전 금요일(실제 조사는 격주 금요일·약 1주 뒤 공개)
function offlinePrice(p) {
  if (p.category !== '생필품') return null;
  const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 2) % 7) - 14);
  return { price: roundPrice(p.base * 1.06, p.base), store_type: '대형마트', survey_date: d.toISOString().slice(0, 10) };
}

function compare(p) {
  const rows = series(p);
  if (!rows.length) return { product_id: p.id, collected_at: null, lowest_total: null, items: [] };
  const last = rows[rows.length - 1];
  const lowest = lowestOf(last);
  const now = new Date(); now.setMinutes(0, 0, 0);
  return {
    product_id: p.id, collected_at: now.toISOString(), lowest_total: lowest,
    items: last.malls.map((m) => ({
      mall_id: m.mall_id, mall: MALLS[m.mall_id - 1].name, price: m.price, shipping_fee: m.shipping_fee, total_price: m.total_price,
      in_stock: m.in_stock, is_lowest: m.in_stock && m.total_price === lowest, url: `https://example.com/mall-${m.mall_id}/products/${p.model_no}`,
      // 가격 비교 사이트(다나와·에누리)만 주는 값. 시연 쇼핑몰은 직접 판매처라 비어 있다(API와 같은 형식)
      offer_count: null, high_price: null, rating: null, review_count: null,
    })).sort((x, y) => (y.in_stock - x.in_stock) || (x.total_price - y.total_price)),
  };
}

function prices(p, days) {
  const rows = series(p).slice(-days);
  const all = series(p).map((r) => ({ date: r.date, v: lowestOf(r) }));
  const min = all.reduce((m, r) => (r.v < m.v ? r : m), all[0] || { v: null, date: null });
  return {
    days, dates: rows.map((r) => r.date),
    malls: MALLS.map((m) => ({ mall: m.name, values: rows.map((r) => (r.malls[m.id - 1].in_stock ? r.malls[m.id - 1].total_price : null)) })),
    lowest: rows.map(lowestOf), all_time_min: { price: min.v, date: min.date },
  };
}

function quota() {
  const q = load(LS.quota, {});
  const key = iso(new Date());
  return { used: q[key] || 0, use() { q[key] = (q[key] || 0) + 1; save(LS.quota, { [key]: q[key] }); return AI_DAILY_LIMIT - q[key]; } };
}

function watchItems() {
  const items = load(LS.watch, null) ?? [
    { id: 1, product_id: 1, target_price: 130000, created_at: new Date(Date.now() - 9 * DAY).toISOString() },
    { id: 2, product_id: 6, target_price: 85000, created_at: new Date(Date.now() - 5 * DAY).toISOString() },
    { id: 3, product_id: 11, target_price: 80000, created_at: new Date(Date.now() - 3 * DAY).toISOString() },
  ];
  if (!localStorage.getItem(LS.watch)) save(LS.watch, items);
  return items;
}

function watchView(w) {
  const p = findProduct(w.product_id);
  const a = analyze(p);
  return { id: w.id, product: publicProduct(p), target_price: w.target_price, current_price: a.current_price, score: a.score,
    label: a.label, reached: a.current_price != null && w.target_price != null && a.current_price <= w.target_price, created_at: w.created_at };
}

function alerts() {
  const read = load(LS.alertsRead, []);
  const items = watchItems().map(watchView).filter((w) => w.reached).map((w) => ({
    id: 1000 + w.id, type: 'TARGET_PRICE', product_id: w.product.id,
    message: `${w.product.name} 실구매가가 ${won(w.current_price)}으로 목표가 ${won(w.target_price)} 이하가 되었습니다.`,
    created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
  }));
  items.push(
    { id: 2001, type: 'TIMING_CHANGE', product_id: 6, message: "에어프라이어 5.5L 판정이 '조금 대기'에서 '지금 구매'로 바뀌었습니다.", created_at: new Date(Date.now() - 26 * 3600000).toISOString() },
    { id: 2002, type: 'TIMING_CHANGE', product_id: 7, message: "무선 청소기 V8은 곧 할인 가능성이 높아 '대기 권장'으로 판정되었습니다.", created_at: new Date(Date.now() - 50 * 3600000).toISOString() },
  );
  const list = items.map((a) => ({ ...a, is_read: read.includes(a.id) }));
  return { unread: list.filter((a) => !a.is_read).length, items: list };
}

function rpaLogs() {
  const rnd = mulberry32(42);
  const daily = []; const logs = [];
  for (let d = 6; d >= 0; d--) {
    const day = new Date(today().getTime() - d * DAY);
    const runs = d === 0 ? new Date().getHours() + 1 : 24;
    const failed = Math.floor(rnd() * 25);
    daily.push({ date: iso(day), runs, success: runs * 900 - failed, failed, collected: runs * 900 - failed });
  }
  const now = new Date(); now.setMinutes(0, 0, 0);
  for (let h = 0; h < 12; h++) {
    const st = new Date(now.getTime() - h * 3600000);
    const failed = Math.floor(rnd() * 6);
    logs.push({ id: 500 - h, job_name: 'collect_prices', status: failed > 4 ? 'PARTIAL' : 'SUCCESS', collected: 900 - failed, failed,
      message: failed > 4 ? '쇼핑몰 C 응답 지연(재시도 후 일부 실패)' : '', started_at: st.toISOString(), ended_at: new Date(st.getTime() + 212000).toISOString() });
  }
  logs.push({ id: 380, job_name: 'train_model', status: 'SUCCESS', collected: 41230, failed: 0, message: 'F1 0.79 (직전 0.78) → 모델 교체', started_at: new Date(today().getTime() + 3 * 3600000).toISOString(), ended_at: new Date(today().getTime() + 3 * 3600000 + 95000).toISOString() });
  logs.push({ id: 379, job_name: 'collect_public_prices', status: 'SUCCESS', collected: 300, failed: 0, message: '참가격 데이터 갱신', started_at: new Date(today().getTime() + 6 * 3600000).toISOString(), ended_at: new Date(today().getTime() + 6 * 3600000 + 41000).toISOString() });
  logs.sort((a, b) => b.started_at.localeCompare(a.started_at));
  const t = today().getTime();
  const total = daily.reduce((s, d) => s + d.collected + d.failed, 0);
  return {
    summary: { runs_today: daily[6].runs, success_rate: Number((1 - daily.reduce((s, d) => s + d.failed, 0) / total).toFixed(4)), collected_today: daily[6].collected, last_run_at: logs[0].started_at },
    daily, logs,
    models: [
      { version: 'rf-' + iso(new Date(t)), algorithm: 'RandomForestClassifier', f1: 0.79, precision: 0.77, trained_rows: 41230, created_at: new Date(t + 3 * 3600000).toISOString(), active: true },
      { version: 'rf-' + iso(new Date(t - DAY)), algorithm: 'RandomForestClassifier', f1: 0.78, precision: 0.76, trained_rows: 40310, created_at: new Date(t - DAY + 3 * 3600000).toISOString(), active: false },
      { version: 'baseline-rule', algorithm: '이동평균 규칙', f1: 0.61, precision: 0.58, trained_rows: 0, created_at: new Date(t - 20 * DAY).toISOString(), active: false },
    ],
  };
}

function aiMetrics() {
  const rnd = mulberry32(7);
  const daily = [];
  for (let d = 6; d >= 0; d--) {
    const calls = 600 + Math.floor(rnd() * 400) - (d < 3 ? 300 : 0);
    daily.push({ date: iso(new Date(today().getTime() - d * DAY)), calls, cache_hits: Math.floor(calls * (d < 3 ? 0.62 : 0.2)),
      avg_latency_ms: Math.round(2100 + rnd() * 600 - (d < 3 ? 300 : 0)), tokens: calls * 1900, validation_fail: d < 3 ? 0 : Math.floor(rnd() * 3) });
  }
  const sum = (k) => daily.reduce((s, d) => s + d[k], 0);
  const recent = PRODUCTS.slice(0, 8).map((p, i) => ({
    created_at: new Date(Date.now() - i * 1500000).toISOString(), type: i % 3 === 2 ? 'CHAT' : 'ADVICE', product: p.name,
    latency_ms: i % 2 ? 48 : 2100 + i * 37, cache_hit: i % 2 === 1, validation: 'OK',
  }));
  return {
    summary: { calls_7d: sum('calls'), avg_latency_ms: Math.round(sum('avg_latency_ms') / 7), tokens_7d: sum('tokens'),
      cache_hit_rate: Number((sum('cache_hits') / sum('calls')).toFixed(3)), validation_fail_rate: Number((sum('validation_fail') / sum('calls')).toFixed(4)), model: 'gemini-2.5-flash (demo)' },
    daily, recent,
  };
}

// ------------------------------------------------------------------ 라우터
const routes = [
  ['POST', /^\/auth\/login$/, (m, body) => {
    const users = load(LS.users, []);
    const email = (body.email || '').trim().toLowerCase();
    const isAdmin = email.startsWith('admin');
    const found = users.find((u) => u.email === email);
    const user = found || { id: isAdmin ? 1 : 2, email, name: isAdmin ? '관리자' : (email.split('@')[0] || '데모 사용자'), role: isAdmin ? 'ADMIN' : 'USER' };
    if (!email) return fail(400, 'VALIDATION_ERROR', '이메일을 입력해 주세요.');
    return ok({ access_token: `demo-${user.role.toLowerCase()}`, token_type: 'bearer', user });
  }],
  ['GET', /^\/auth\/providers$/, () => ok({ demo_login: true, google: false, naver: false, kakao: false })],
  ['POST', /^\/auth\/demo-login$/, (m, body) => {
    const admin = body.kind === 'admin';
    const user = admin ? { id: 1, email: 'admin@timepick.demo', name: '관리자', role: 'ADMIN' } : { id: 2, email: 'demo@timepick.demo', name: '데모 사용자', role: 'USER' };
    return ok({ access_token: `demo-${user.role.toLowerCase()}`, token_type: 'bearer', user });
  }],
  ['POST', /^\/auth\/signup$/, (m, body) => {
    const users = load(LS.users, []);
    const email = (body.email || '').trim().toLowerCase();
    if (!PASSWORD_RULE.test(body.password || '')) return fail(422, 'VALIDATION_ERROR', '비밀번호는 영문 대문자·소문자·숫자·특수문자를 모두 포함해 8자 이상이어야 합니다.');
    if (users.some((u) => u.email === email)) return fail(409, 'EMAIL_EXISTS', '이미 가입된 이메일입니다.');
    const user = { id: 100 + users.length, email, name: body.name || email.split('@')[0], role: 'USER' };
    save(LS.users, [...users, user]);
    return ok(user, 201);
  }],
  ['GET', /^\/users\/me$/, (m, b, token) => ok(JSON.parse(localStorage.getItem('pt_user') || 'null') || { id: 2, email: 'demo@timepick.demo', name: 'demo', role: token === 'demo-admin' ? 'ADMIN' : 'USER' })],
  ['GET', /^\/products\/search$/, (m, b, t, query) => {
    // 서버(GET /products/search)와 같은 규칙: 분류(쉼표 여러 개)·지금 구매·정렬을 전체에 적용한 뒤 page 단위로 자른다
    const q = (query.get('q') || '').trim().toLowerCase();
    const cats = (query.get('category') || '').split(',').map((c) => c.trim()).filter(Boolean);
    const sort = ['score', 'price'].includes(query.get('sort')) ? query.get('sort') : 'id';
    const size = Math.min(100, Math.max(1, Number(query.get('size')) || 50)); const page = Math.max(1, Number(query.get('page')) || 1);
    const items = allProducts().filter((p) => (!q || `${p.name} ${p.brand} ${p.category} ${p.model_no}`.toLowerCase().includes(q)) && (!cats.length || cats.includes(p.category)))
      .map((p) => { const a = analyze(p); return { ...publicProduct(p), lowest_price: a.current_price, score: a.score, label: a.label }; })
      .filter((p) => query.get('buy_only') !== 'true' || p.label === 'BUY_NOW')
      .sort((a, b) => sort === 'score' ? (b.score ?? -1) - (a.score ?? -1) || a.id - b.id
        : sort === 'price' ? (a.lowest_price ?? Infinity) - (b.lowest_price ?? Infinity) || a.id - b.id : a.id - b.id);
    return ok({ items: items.slice((page - 1) * size, page * size), total: items.length, page, size });
  }],
  ['POST', /^\/products$/, (m, body) => {
    const url = (body.url || '').trim();
    if (!/^https?:\/\//.test(url)) return fail(400, 'INVALID_URL', 'http(s)로 시작하는 상품 URL을 입력해 주세요.');
    const custom = load(LS.custom, []);
    const p = { id: 1000 + custom.length + 1, name: body.name?.trim() || '등록 상품', brand: '-', model_no: '-', category: '기타', base: 0, days: 0 };
    save(LS.custom, [...custom, p]);
    return ok({ product: publicProduct(p), status: 'PENDING', message: '다음 수집 주기(하루 4회: 0·6·12·18시)부터 가격이 반영됩니다.' }, 201);
  }],
  ['GET', /^\/products\/(\d+)$/, (m) => {
    const p = findProduct(m[1]);
    return p ? ok({ ...publicProduct(p), listings_count: p.days ? MALLS.length : 0, spec_summary: p.spec || null, offline_price: offlinePrice(p) }) : fail(404, 'PRODUCT_NOT_FOUND', '상품을 찾을 수 없습니다.');
  }],
  ['GET', /^\/products\/(\d+)\/compare$/, (m) => { const p = findProduct(m[1]); return p ? ok(compare(p)) : fail(404, 'PRODUCT_NOT_FOUND', '상품을 찾을 수 없습니다.'); }],
  ['GET', /^\/products\/(\d+)\/prices$/, (m, b, t, query) => {
    const p = findProduct(m[1]);
    const days = [7, 30, 90].includes(Number(query.get('days'))) ? Number(query.get('days')) : 90;
    return p ? ok(prices(p, days)) : fail(404, 'PRODUCT_NOT_FOUND', '상품을 찾을 수 없습니다.');
  }],
  ['GET', /^\/products\/(\d+)\/timing$/, (m) => { const p = findProduct(m[1]); return p ? ok(analyze(p)) : fail(404, 'PRODUCT_NOT_FOUND', '상품을 찾을 수 없습니다.'); }],
  ['POST', /^\/products\/(\d+)\/advice$/, async (m) => {
    const p = findProduct(m[1]);
    if (!p) return fail(404, 'PRODUCT_NOT_FOUND', '상품을 찾을 수 없습니다.');
    const q = quota();
    if (q.used >= AI_DAILY_LIMIT) return fail(429, 'AI_LIMIT_EXCEEDED', `AI 사용 한도(일 ${AI_DAILY_LIMIT}회)를 초과했습니다.`);
    await sleep(900);
    return ok({ ...advice(analyze(p)), cached: false, source: 'demo-template', remaining: q.use() });
  }],
  ['POST', /^\/ai\/chat$/, async (m, body) => {
    const p = findProduct(body.product_id);
    if (!p) return fail(404, 'PRODUCT_NOT_FOUND', '상품을 찾을 수 없습니다.');
    const question = (body.question || '').trim();
    if (!question || question.length > 200) return fail(400, 'VALIDATION_ERROR', '질문은 1~200자로 입력해 주세요.');
    const q = quota();
    if (q.used >= AI_DAILY_LIMIT) return fail(429, 'AI_LIMIT_EXCEEDED', `AI 사용 한도(일 ${AI_DAILY_LIMIT}회)를 초과했습니다.`);
    await sleep(800);
    return ok({ answer: chatAnswer(p, analyze(p), question), source: 'demo-template', remaining: q.use() });
  }],
  ['GET', /^\/watchlist$/, () => ok({ items: watchItems().map(watchView) })],
  ['POST', /^\/watchlist$/, (m, body) => {
    const items = watchItems();
    const p = findProduct(body.product_id);
    if (!p) return fail(404, 'PRODUCT_NOT_FOUND', '상품을 찾을 수 없습니다.');
    if (items.some((w) => w.product_id === p.id)) return fail(409, 'ALREADY_WATCHING', '이미 관심 상품으로 등록되어 있습니다.');
    const w = { id: Math.max(0, ...items.map((i) => i.id)) + 1, product_id: p.id, target_price: body.target_price ? Number(body.target_price) : null, created_at: new Date().toISOString() };
    save(LS.watch, [...items, w]);
    return ok(watchView(w), 201);
  }],
  ['PATCH', /^\/watchlist\/(\d+)$/, (m, body) => {
    const items = watchItems();
    const w = items.find((i) => i.id === Number(m[1]));
    if (!w) return fail(404, 'NOT_FOUND', '관심 상품을 찾을 수 없습니다.');
    w.target_price = body.target_price ? Number(body.target_price) : null;
    save(LS.watch, items);
    return ok(watchView(w));
  }],
  ['DELETE', /^\/watchlist\/(\d+)$/, (m) => { save(LS.watch, watchItems().filter((i) => i.id !== Number(m[1]))); return ok(null, 204); }],
  ['GET', /^\/alerts$/, () => ok(alerts())],
  ['POST', /^\/alerts\/read-all$/, () => { const all = alerts().items.map((a) => a.id); save(LS.alertsRead, all); return ok({ updated: all.length }); }],
  ['GET', /^\/deals\/today$/, () => {
    const analyzed = PRODUCTS.map((p) => ({ p, a: analyze(p) })).filter(({ a }) => a.score != null);
    const timing = analyzed.sort((x, y) => y.a.score - x.a.score).slice(0, 6)
      .map(({ p, a }) => ({ ...publicProduct(p), current_price: a.current_price, score: a.score, label: a.label }));
    const drops = PRODUCTS.filter((p) => p.days >= 8).map((p) => {
      const s = series(p).map(lowestOf);
      return { ...publicProduct(p), current_price: s[s.length - 1], change_7d: Number((s[s.length - 1] / s[s.length - 8] - 1).toFixed(4)) };
    }).sort((x, y) => x.change_7d - y.change_7d).slice(0, 6);
    return ok({ timing, drops });
  }],
  ['GET', /^\/admin\/collect$/, (m, b, token) => (token === 'demo-admin' ? ok({ allowed: false, configured: false, reason: '테스트 관리자 계정은 조회만 가능합니다. 실제 관리자 계정으로 로그인해 주세요.', last_requested_at: null }) : fail(403, 'FORBIDDEN', '관리자 권한이 필요합니다.'))],
  ['POST', /^\/admin\/collect$/, () => fail(403, 'DEMO_READ_ONLY', '테스트 관리자 계정은 조회만 가능합니다. 실제 관리자 계정으로 로그인해 주세요.')],
  ['GET', /^\/admin\/rpa-logs$/, (m, b, token) => (token === 'demo-admin' ? ok(rpaLogs()) : fail(403, 'FORBIDDEN', '관리자 권한이 필요합니다.'))],
  ['GET', /^\/admin\/ai-metrics$/, (m, b, token) => (token === 'demo-admin' ? ok(aiMetrics()) : fail(403, 'FORBIDDEN', '관리자 권한이 필요합니다.'))],
  ['GET', /^\/admin\/users$/, (m, b, token, query) => {
    if (token !== 'demo-admin') return fail(403, 'FORBIDDEN', '관리자 권한이 필요합니다.');
    const q = (query.get('q') || '').toLowerCase();
    const role = query.get('role') || '';
    const items = mockUsers().filter((u) => (!q || u.email.includes(q) || u.name.toLowerCase().includes(q)) && (!role || u.role === role));
    return ok({ items, total: items.length, page: 1, size: 20, summary: { users: mockUsers().length, admins: mockUsers().filter((u) => u.role === 'ADMIN').length } });
  }],
  ['PATCH', /^\/admin\/users\/(\d+)\/role$/, () => fail(403, 'DEMO_READ_ONLY', '테스트 관리자 계정은 회원 권한을 변경할 수 없습니다(조회만 가능).')],
];

function mockUsers() {
  const base = [
    { id: 1, email: 'admin@timepick.demo', name: '관리자', role: 'ADMIN', watch_count: 0 },
    { id: 2, email: 'demo@timepick.demo', name: '데모 사용자', role: 'USER', watch_count: watchItems().length },
  ];
  const extra = load(LS.users, []).map((u) => ({ ...u, watch_count: 0 }));
  return [...extra.reverse(), ...base].map((u) => ({ created_at: new Date(Date.now() - u.id * DAY).toISOString(), ...u }));
}

export async function handleMock(method, fullPath, body = {}, token = null) {
  const [path, qstr = ''] = fullPath.split('?');
  await sleep(120);
  const open = path.startsWith('/auth/') || path === '/deals/today'; // 백엔드와 같은 공개 경로
  if (!open && !token) return fail(401, 'UNAUTHORIZED', '로그인이 필요합니다.');
  for (const [meth, re, fn] of routes) {
    const m = path.match(re);
    if (m && meth === method) return fn(m, body || {}, token, new URLSearchParams(qstr));
  }
  return fail(404, 'NOT_FOUND', `데모 API에 없는 경로입니다: ${method} ${path}`);
}
