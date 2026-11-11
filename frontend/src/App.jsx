import { Component, Suspense, createContext, lazy, useCallback, useContext, useEffect, useId, useRef, useState } from 'react';
import { Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api, auth, DEMO, oauthStartUrl } from './lib/api.js';
import { AuthProvider, useAuth } from './lib/auth.jsx';
import { ToastProvider, useToast } from './components/Toast.jsx';
import { t, LANG, LOCALE, money, setLang } from './lib/i18n.js';
import { applyTheme, currentTheme } from './lib/theme.js';

// 고객 화면과 공통 인터랙션을 한 파일에 구성한다. 기존 관리자 도구는 필요할 때 로드한다.
const Admin = lazy(() => import('./pages/Admin.jsx'));
const AdminAI = lazy(() => import('./pages/AdminAI.jsx'));
const AdminUsers = lazy(() => import('./pages/AdminUsers.jsx'));
const UIContext = createContext(null);
const CATEGORIES = [
  { name: '디지털', icon: 'headphones', caption: t("이어폰 · 헤드폰"), photo: 'photo-1505740420928-5e560c06d30e' },
  { name: '가전', icon: 'plug', caption: t("생활을 편리하게"), photo: 'photo-1556911220-bff31c812dba' },
  { name: '생필품', icon: 'basket-shopping', caption: t("매일 필요한 것"), photo: 'photo-1542838132-92c53300491e' },
  { name: '패션', icon: 'shirt', caption: t("취향을 담은 선택"), photo: 'photo-1542291026-7eec264c27ff' },
  { name: '유아', icon: 'baby', caption: t("가족을 위한 쇼핑"), photo: 'photo-1515488042361-ee00e0ddd4e4' },
];
const PAGE_SIZE = 24; // 상품 탐색 한 페이지 상품 수(4열 × 6줄)
const MIN_LOW_DAYS = 30; // '역대 최저가' 배지를 붙이려면 필요한 가격 이력 일수(적기 판단 최소 이력과 같음)
const SIGNALS = {
  BUY_NOW: { text: t("지금 사세요"), icon: 'fire-flame-curved', color: 'text-emerald-700 bg-emerald-50', stroke: '#059669', note: t("과거 가격 흐름상 구매하기 좋은 구간입니다.") },
  WAIT_A_BIT: { text: t("조금 더 지켜보세요"), icon: 'hourglass-half', color: 'text-rose-700 bg-rose-50', stroke: '#e11d48', note: t("급하지 않다면 목표가를 정하고 기다려 보세요.") },
  WAIT: { text: t("가격 관망 필요"), icon: 'hand', color: 'text-rose-700 bg-rose-50', stroke: '#e11d48', note: t("추가 가격 하락 가능성을 살펴볼 시점입니다.") },
  HOLD: { text: t("분석 준비 중"), icon: 'clock', color: 'text-slate-600 bg-slate-100', stroke: '#64748b', note: t("판단에 필요한 가격 이력이 아직 부족합니다.") },
};
const won = (v) => Number.isFinite(v) ? money(v) : t("수집 대기");
const percent = (v) => Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : '—';
const dateText = (v) => v ? new Date(v).toLocaleString(LOCALE, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : t("수집 대기");
const priceOf = (p) => p?.current_price ?? p?.lowest_price ?? null;
const signalOf = (p) => SIGNALS[p?.label] || SIGNALS.HOLD;
const safeNext = (v) => /^\/(?!\/)/.test(v || '') && !/[\\\u0000-\u001f]/.test(v) ? v : '/';
const safeUrl = (v) => /^https?:\/\//i.test(v || '') ? v : null;
const PASSWORD_CHECKS = [
  [t("8자 이상"), (p) => p.length >= 8 && p.length <= 72], [t("대문자"), (p) => /[A-Z]/.test(p)],
  [t("소문자"), (p) => /[a-z]/.test(p)], [t("숫자"), (p) => /[0-9]/.test(p)], [t("특수문자"), (p) => /[^A-Za-z0-9\s]/.test(p)],
];
const photoUrl = (id, width = 700) => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${width}&q=80`;
const Icon = ({ name, className = '' }) => <i className={`fa-solid fa-${name} ${className}`} aria-hidden="true" />;

// 경로·계정·갱신 번호별로 응답을 구분해 늦게 도착한 이전 검색 결과를 무시한다.
function useApi(path, revision = 0) {
  const { user } = useAuth();
  const key = `${path}|${user?.id ?? 'guest'}|${revision}`;
  const [result, setResult] = useState({ key: null });
  useEffect(() => {
    if (!path) return;
    let active = true;
    api.get(path).then((data) => { if (active) setResult({ key, data }); })
      .catch((error) => { if (active) setResult({ key, error }); });
    return () => { active = false; };
  }, [path, key]);
  return result.key === key ? { ...result, loading: false } : { loading: !!path, data: null, error: null };
}
function Loading({ text = t("가격 정보를 불러오고 있어요") }) {
  return <div role="status" className="flex min-h-32 items-center justify-center gap-3 p-6 text-sm text-slate-500"><Icon name="circle-notch" className="animate-spin" />{text}</div>;
}
function Notice({ error, retry }) {
  if (!error) return null;
  return <div role="alert" className="my-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"><Icon name="circle-exclamation" className="mr-2" />{error.message || String(error)}
    {retry && <button className="btn-ghost ml-2 text-rose-800" onClick={retry}>{t("다시 시도")}</button>}</div>;
}
function Empty({ title, children, icon = 'magnifying-glass' }) {
  return <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 px-5 py-12 text-center">
    <Icon name={icon} className="mb-4 text-2xl text-slate-400" /><h3 className="text-lg">{title}</h3><div className="mt-2 text-sm leading-relaxed text-slate-500">{children}</div></div>;
}
function Brand({ light = false }) {
  return <Link to="/" className={`inline-flex shrink-0 items-center gap-2.5 ${light ? 'text-white' : 'text-slate-900'}`} aria-label={t("TimePick 홈")}>
    <span className="flex size-10 items-center justify-center rounded-xl bg-brand-600 text-lg text-white"><Icon name="clock-rotate-left" /></span>
    <span className="font-display text-[23px] font-medium tracking-[-0.035em]">TimePick<span className="ml-1 text-brand-500">.</span></span></Link>;
}
function Signal({ product, score = false }) {
  const s = signalOf(product);
  return <span className={`badge ${s.color}`}><Icon name={s.icon} />{s.text}{score && Number.isFinite(product.score) && t(" · {n}점", { n: product.score })}</span>;
}
function PriceChange({ value }) {
  if (!Number.isFinite(value)) return null;
  return <span className={`numeric inline-flex items-center gap-1 text-sm ${value < 0 ? 'text-emerald-600' : value > 0 ? 'text-rose-600' : 'text-slate-500'}`}>
    <Icon name={value < 0 ? 'arrow-down' : value > 0 ? 'arrow-up' : 'minus'} />{percent(Math.abs(value))}</span>;
}
function imageSource(url) {
  // 이미지 출처 표시: 제조사 공식 이미지를 우선 등록하고, 찾지 못한 상품만 가격 비교 사이트(다나와·에누리) 상품 이미지를 쓴다
  const host = (() => { try { return new URL(url).hostname; } catch { return ''; } })();
  // 다나와·에누리는 같은 회사(커넥트웨이브)가 운영하며 이미지 서버(img.danuri.io)도 함께 쓴다
  if (/(^|\.)unsplash\.com$/.test(host)) return t("참고 이미지 · Unsplash"); // 데모 모드 가상 상품
  return /(^|\.)(danawa\.com|danuri\.io|enuri\.(com|info))$/.test(host) ? t("이미지: 다나와·에누리") : t("제조사 이미지");
}
function Photo({ product, className = '', caption = true }) {
  // 실제 사진은 catalog.json에 등록한 image_url만 쓴다(제조사 공식 우선, 없으면 다나와·에누리). 없거나 깨지면 카테고리 아이콘
  const [failed, setFailed] = useState(false);
  const icon = (CATEGORIES.find((c) => c.name === product.category) || { icon: 'box-open' }).icon;
  const official = product.image_url && !failed;
  return <div className={`product-photo ${className}`}>
    {official ? <img src={product.image_url} alt={product.name || t("상품")} width="700" height="525" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(true)} style={{ objectFit: 'contain' }} />
      : <div className="flex h-full min-h-32 flex-col items-center justify-center gap-2 text-slate-400" role="img" aria-label={t("{c} 카테고리", { x: '', c: t(product.category || "상품") })}>
          <Icon name={icon} className="text-4xl" /><span className="text-xs">{t(product.category || "상품")}</span></div>}
    {caption && official && <span className="absolute bottom-2 right-2 whitespace-nowrap rounded bg-white/90 px-1.5 py-0.5 text-[10px] text-slate-600">{imageSource(product.image_url)}</span>}</div>;
}
function Dialog({ open, title, onClose, drawer = false, children }) {
  const ref = useRef(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const node = ref.current; const previous = document.activeElement; const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden'; node.showModal();
    return () => { node.close(); document.body.style.overflow = overflow; previous?.focus?.(); };
  }, [open]);
  function containFocus(e) {
    if (e.key !== 'Tab') return;
    const controls = [...ref.current.querySelectorAll('button, a[href], input, select, textarea, [tabindex]')]
      .filter((node) => !node.disabled && node.tabIndex >= 0 && node.getClientRects().length);
    const first = controls[0]; const last = controls.at(-1);
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
  }
  return open && <dialog ref={ref} className={`modal ${drawer ? 'drawer' : ''}`} aria-labelledby={titleId}
    onKeyDown={containFocus} onCancel={(e) => { e.preventDefault(); onClose(); }} onClick={(e) => { if (e.target === ref.current) onClose(); }}>
    <div className="p-6 sm:p-8"><div className="mb-6 flex items-center justify-between gap-3"><h2 id={titleId} className="text-xl">{title}</h2>
      <button className="icon-btn -mr-2" onClick={onClose} aria-label={t("{x} 닫기", { x: title })}><Icon name="xmark" /></button></div>{children}</div></dialog>;
}
function SearchBar({ name, large = false, initial = '' }) {
  const nav = useNavigate(); const [q, setQ] = useState(initial); const [category, setCategory] = useState('');
  useEffect(() => setQ(initial), [initial]);
  return <form role="search" aria-label={name} className={`flex min-w-0 items-center gap-2 rounded-2xl border border-slate-200 bg-white p-1.5 ${large ? 'shadow-sm' : ''}`}
    onSubmit={(e) => { e.preventDefault(); const params = new URLSearchParams({ q: q.trim() }); if (category) params.set('category', category); nav(`/search?${params}`); }}>
    <Icon name="magnifying-glass" className="ml-3 shrink-0 text-slate-400" />
    <input type="search" aria-label={name} className="min-w-0 flex-1 bg-transparent py-2.5 text-sm outline-none" placeholder={t("어떤 상품의 가격이 궁금하세요?")} maxLength={100} value={q} onChange={(e) => setQ(e.target.value)} />
    {!large && <select aria-label={t("{x} 카테고리", { x: name })} className="select-x hidden max-w-28 border-transparent bg-slate-50 text-xs text-slate-600 xl:block" value={category} onChange={(e) => setCategory(e.target.value)}><option value="">{t("전체")}</option>{CATEGORIES.map((c) => <option key={c.name}>{t(c.name)}</option>)}</select>}
    {large ? <button className="btn-primary">{t("가격 검색")}<Icon name="arrow-right" /></button> : <button className="icon-btn text-brand-600" aria-label={t("검색")}><Icon name="arrow-right" /></button>}</form>;
}
function Header() {
  const { user, logout } = useAuth(); const { revision } = useContext(UIContext);
  const [open, setOpen] = useState(false); const location = useLocation();
  const alerts = useApi(user ? '/alerts' : null, revision);
  useEffect(() => setOpen(false), [location.pathname, location.search]);
  const navItems = [['/', t("발견"), 'compass'], ['/search', t("가격 비교"), 'chart-simple'], ['/watchlist', t("관심 상품"), 'heart'], ['/alerts', t("가격 알림"), 'bell']];
  const links = (mobile) => navItems.map(([to, text, icon]) => <NavLink end={to === '/'} to={to} key={to}
    className={({ isActive }) => `${mobile ? 'flex rounded-xl px-4 py-3' : 'inline-flex border-b-2 py-4'} items-center gap-2 text-sm ${isActive ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-900'}`}>
    <Icon name={icon} />{text}{to === '/alerts' && alerts.data?.unread > 0 && <span className="rounded-full bg-rose-50 px-1.5 text-xs text-rose-700">{alerts.data.unread}</span>}</NavLink>);
  return <>
    {DEMO && <div className="keep-dark bg-slate-900 px-4 py-2 text-center text-[11px] text-slate-200">{t("TimePick 체험 공간 · 상품과 가격은 데모 데이터입니다")}</div>}
    <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/85 backdrop-blur-md">
      <div className="container-x flex h-20 items-center gap-6"><Brand /><div className="ml-5 hidden max-w-xl flex-1 md:block"><SearchBar name={t("헤더 상품 검색")} /></div>
        <div className="ml-auto hidden items-center gap-2 lg:flex"><Preferences />{user ? <><span className="max-w-28 truncate text-sm text-slate-600">{user.name}{" "}{t("님")}</span><button className="btn-ghost" onClick={logout}>{t("로그아웃")}</button></>
          : <><Link to="/login" className="btn-ghost">{t("로그인")}</Link><Link to="/signup" className="btn-primary">{t("시작하기")}</Link></>}</div>
        <button className="icon-btn ml-auto lg:hidden" onClick={() => setOpen(true)} aria-label={t("메뉴 열기")} aria-expanded={open}><span className={`hamburger ${open ? 'is-open' : ''}`}><span /><span /><span /></span></button>
      </div>
      <div className="container-x hidden items-center justify-between lg:flex"><nav className="flex gap-8" aria-label={t("주 메뉴")}>{links(false)}</nav>
        <div className="flex items-center gap-2 text-xs text-slate-500"><span className="size-1.5 rounded-full bg-emerald-500" />{t("가격 수집 · 하루 4회")}{user?.role === 'ADMIN' && <Link to="/admin" className="ml-4 py-3 text-brand-700">{t("관리자 센터")}<Icon name="angle-right" className="ml-2" /></Link>}</div></div>
    </header>
    <Dialog open={open} title={t("메뉴")} onClose={() => setOpen(false)} drawer><SearchBar name={t("모바일 상품 검색")} /><nav className="mt-5 space-y-2" aria-label={t("모바일 메뉴")}>{links(true)}</nav>
      {user?.role === 'ADMIN' && <Link className="btn-ghost mt-3 w-full" to="/admin">{t("관리자 센터")}</Link>}
      <div className="mt-6 border-t border-slate-200 pt-5"><div className="mb-4"><Preferences wide /></div>{user ? <><p className="mb-3 text-sm">{user.name}{" "}{t("님, 반가워요.")}</p><button className="btn-outline w-full" onClick={() => { logout(); setOpen(false); }}>{t("로그아웃")}</button></>
        : <div className="grid gap-2"><Link className="btn-primary" to="/login">{t("로그인")}</Link><Link className="btn-outline" to="/signup">{t("회원가입")}</Link></div>}</div></Dialog>
  </>;
}
function Footer() {
  return <footer className="keep-dark mt-20 bg-slate-900 text-slate-300">
    <div className="container-x grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-[1.6fr_1fr_1fr_1.2fr]">
      <div><Brand light /><p className="mt-5 max-w-xs text-sm leading-7">{t("좋은 가격에, 좋은 타이밍에.")}<br />{t("데이터로 더 여유로운 쇼핑을 만듭니다.")}</p>
        <a href="https://github.com/fsclass-n/timepick" target="_blank" rel="noreferrer" className="mt-4 inline-flex size-11 items-center justify-center rounded-full border border-slate-700 hover:bg-slate-800" aria-label="TimePick GitHub"><i className="fa-brands fa-github" aria-hidden="true" /></a></div>
      <div><h2 className="mb-4 text-sm text-white">{t("가격 탐색")}</h2><ul className="space-y-3 text-sm"><li><Link to="/search">{t("모든 상품 비교")}</Link></li><li><Link to="/?view=drops#discover">{t("최근 가격 하락")}</Link></li><li><Link to="/watchlist">{t("내 관심 상품")}</Link></li><li><Link to="/alerts">{t("목표가 알림")}</Link></li></ul></div>
      <div><h2 className="mb-4 text-sm text-white">{t("이용 안내")}</h2><ul className="space-y-3 text-sm"><li><Link to="/guide">{t("구매 타이밍 이해하기")}</Link></li><li><Link to="/privacy">{t("개인정보 처리 안내")}</Link></li><li><Link to="/terms">{t("서비스 이용 안내")}</Link></li><li><a href="https://github.com/fsclass-n/timepick/issues" target="_blank" rel="noreferrer">{t("문제 제보")}</a></li></ul></div>
      <div><h2 className="mb-4 text-sm text-white">{t("데이터 기준")}</h2><p className="text-xs leading-6">{t("다나와·에누리 상품 페이지에서 하루 4회(0·6·12·18시) 수집합니다. 판매처 최저가를 비교하며, 최종 결제 금액은 판매처에서 확인해 주세요.")}</p><p className="mt-3 text-xs leading-6 text-slate-400">{t("상품 이미지는 제조사 공식 이미지이며, 찾지 못한 상품은 다나와·에누리 상품 이미지를 출처와 함께 보여 줍니다(데모 모드는 Unsplash 참고 이미지). 구매 적기 예측은 참고 정보이며 미래 가격을 보장하지 않습니다.")}</p></div>
    </div>
    <div className="container-x flex flex-wrap items-center justify-between gap-4 border-t border-slate-700 py-6 text-xs text-slate-400"><span>© {new Date().getFullYear()}{" "}{t("TimePick · Final-Project 3조")}</span><span>{t("박미금 · 김모란 · 이오리 · 홍기흥")}</span>
      <button className="btn-ghost text-slate-300 hover:bg-slate-800 hover:text-white" onClick={() => window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })}>{t("맨 위로")}<Icon name="arrow-up" /></button></div>
  </footer>;
}

// 누락값을 연결하거나 미래 가격을 임의로 생성하지 않고 관측된 가격만 그린다.
function PriceChart({ data, mini = false }) {
  const gradient = useId().replace(/:/g, ''); const [point, setPoint] = useState(null); const [mall, setMall] = useState('');
  const values = mall ? data?.malls?.find((m) => m.mall === mall)?.values : data?.lowest;
  const valid = (values || []).filter((v) => Number.isFinite(v) && v > 0);
  if (!valid.length) return mini ? null : <Empty title={t("아직 가격 이력이 없어요")}>{t("다음 수집 후 차트가 표시됩니다.")}</Empty>;
  const w = 600; const h = mini ? 88 : 245; const l = mini ? 0 : 68; const top = 20; const bottom = h - (mini ? 10 : 35);
  const min = Math.min(...valid); const max = Math.max(...valid); const padding = Math.max((max - min) * 0.2, max * 0.015, 1); const low = min - padding; const high = max + padding;
  const x = (i) => l + i / Math.max(1, values.length - 1) * (w - l - 16);
  const y = (v) => top + (high - v) / (high - low) * (bottom - top);
  let previous = false;
  const line = values.map((v, i) => { if (!(Number.isFinite(v) && v > 0)) { previous = false; return ''; } const s = `${previous ? 'L' : 'M'}${x(i)},${y(v)}`; previous = true; return s; }).join(' ');
  const active = Math.min(point ?? values.length - 1, values.length - 1); const color = valid.at(-1) <= valid[0] ? '#059669' : '#e11d48';
  return <div className="min-w-0">
    {!mini && <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500"><span>{data.dates[active]} <span className="numeric ml-2 text-sm text-slate-900">{won(values[active])}</span></span>
      <select className="select-x min-h-11 max-w-48" value={mall} onChange={(e) => { setMall(e.target.value); setPoint(null); }} aria-label={t("차트 판매처")}><option value="">{t("최저 실구매가")}</option>{data.malls?.map((m) => <option key={m.mall}>{m.mall}</option>)}</select></div>}
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full overflow-visible" role="img" aria-label={mini ? t("최근 90일 최저가 추이") : t("가격 변동 차트")}>
      <title>{t("최저 {min}, 최고 {max}, 마지막 관측 {last}", { min: won(min), max: won(max), last: won(valid.at(-1)) })}</title>
      <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop stopColor={color} stopOpacity=".13" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      {!mini && [0, 0.5, 1].map((r) => <g key={r}><line x1={l} x2={w - 16} y1={top + r * (bottom - top)} y2={top + r * (bottom - top)} className="chart-grid" /><text x={l - 10} y={top + r * (bottom - top) + 4} textAnchor="end" className="chart-text">{Math.round(high - r * (high - low)).toLocaleString(LOCALE)}</text></g>)}
      {valid.length === values.length && <path d={`${line} L${x(values.length - 1)},${bottom} L${x(0)},${bottom}Z`} fill={`url(#${gradient})`} />}
      <path d={line} className="chart-line" stroke={color} strokeWidth={mini ? 4 : 2.5} />
      {Number.isFinite(values[active]) && <circle cx={x(active)} cy={y(values[active])} r={mini ? 4 : 5} fill={color} stroke="white" strokeWidth="2" />}
      {!mini && <><text x={l} y={h - 8} className="chart-text">{data.dates[0]?.slice(5)}</text><text x={w - 16} y={h - 8} textAnchor="end" className="chart-text">{data.dates.at(-1)?.slice(5)}</text></>}
    </svg>
    {!mini && <input type="range" min="0" max={Math.max(0, values.length - 1)} value={active} onChange={(e) => setPoint(Number(e.target.value))} className="h-6 w-full" aria-label={t("날짜별 가격 탐색")} aria-valuetext={`${data.dates[active]}, ${won(values[active])}`} />}
  </div>;
}
function TimingGauge({ timing, compact = false }) {
  const s = signalOf(timing); const score = Number.isFinite(timing?.score) ? Math.max(0, Math.min(100, timing.score)) : null;
  return <div className={compact ? '' : 'rounded-2xl bg-slate-50 p-5'}>
    <div className="flex items-center justify-between gap-2"><Signal product={timing} /><span className="numeric text-xl">{score ?? '—'}<span className="ml-1 text-xs text-slate-500">/ 100</span></span></div>
    <div role="meter" aria-label={t("구매 적기 점수")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={score ?? 0} aria-valuetext={score == null ? t("분석 준비 중") : t("{n}점", { n: score })} className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200"><div className="h-full rounded-full" style={{ width: `${score ?? 0}%`, background: s.stroke }} /></div>
    <div className="mt-2 flex justify-between text-[11px] text-slate-500"><span>{t("기다려도 좋아요")}</span><span>{t("지금이 좋아요")}</span></div>
    {!compact && <p className="mt-4 text-xs leading-6 text-slate-500">{s.note}{" "}{t("점수는 구매 적합도이며 예측 확률이 아닙니다.")}</p>}</div>;
}
function ProductCard({ product: p }) {
  const { user } = useAuth(); const { openWatch } = useContext(UIContext);
  const card = useRef(null); const [visible, setVisible] = useState(false);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setVisible(true); observer.disconnect(); } }, { rootMargin: '200px' });
    observer.observe(card.current);
    return () => observer.disconnect();
  }, []);
  const history = useApi(user && visible ? `/products/${p.id}/prices?days=90` : null);
  const current = priceOf(p); const allTime = history.data?.all_time_min?.price;
  // 수집한 지 얼마 안 된 상품은 현재가가 곧 최저가라 '역대 최저가'가 무의미하다 → 30일 이상 이력이 있을 때만 표시
  const atLow = Number.isFinite(current) && current > 0 && Number.isFinite(allTime) && current <= allTime && (history.data?.dates?.length || 0) >= MIN_LOW_DAYS;
  return <article ref={card} className="group min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white transition-shadow duration-200 hover:shadow-lg hover:shadow-slate-200/50">
    <div className="relative"><Link to={`/product/${p.id}`} tabIndex={-1} aria-hidden="true"><Photo product={p} /></Link>
    <div className="absolute left-3 right-14 top-3 flex flex-wrap gap-2">{atLow && <span className="badge bg-emerald-600 text-white"><Icon name="arrow-trend-down" />{t("역대 최저가")}</span>}
        {p.score != null && <span className="badge bg-white/95 text-brand-700"><Icon name="wand-magic-sparkles" />{t("적기")}{" "}{p.score}{t("점")}</span>}</div>
      <button className="icon-btn absolute right-2 top-2 bg-white/95 shadow-sm" onClick={() => openWatch(p)} aria-label={t("{x} 목표가 알림", { x: p.name })}><Icon name="bell" /></button></div>
    <div className="p-5"><p className="mb-1 text-xs text-slate-500">{p.brand || p.category} <span className="mx-1 text-slate-300">/</span> {t(p.category)}</p>
      <Link to={`/product/${p.id}`} className="hover:text-brand-700"><h3 className="line-clamp-2 min-h-12 text-base leading-6" title={p.name}>{p.name}</h3></Link>
      <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2"><span className="numeric text-[23px]">{won(current)}</span><PriceChange value={p.change_7d} /></div>
      <div className="mt-4 border-t border-slate-100 pt-3">{p.label ? <Signal product={p} /> : <span className="text-xs text-slate-500">{t("7일 전 가격 대비")}</span>}
        {history.data && <div className="mt-2"><PriceChart data={history.data} mini /></div>}
        {history.error && <p className="mt-2 text-xs text-slate-500">{t("차트를 불러오지 못했습니다. 상세에서 다시 확인하세요.")}</p>}</div></div></article>;
}
function CompareTable({ data, compact = false }) {
  if (!data?.items?.length) return <Empty title={t("수집된 판매처 가격이 없습니다")} icon="store">{t("가격이 수집되면 배송비를 포함해 비교합니다.")}</Empty>;
  return <div className="relative overflow-x-auto" tabIndex={0} role="region" aria-label={t("판매처 가격 비교 표")}><table className="table-x"><caption className="sr-only">{t("쇼핑몰별 판매가, 배송비, 실구매가 비교")}</caption>
    <thead><tr><th scope="col">{t("판매처")}</th>{!compact && <><th scope="col" className="text-right">{t("판매가")}</th><th scope="col" className="text-right">{t("배송비")}</th></>}<th scope="col" className="text-right">{t("실구매가")}</th>{!compact && <th scope="col"><span className="sr-only">{t("구매 링크")}</span></th>}</tr></thead>
    <tbody>{data.items.slice(0, compact ? 3 : undefined).map((i) => <tr key={i.mall_id ?? i.mall} className={i.is_lowest ? 'bg-emerald-50/50' : ''}>
      <td><span className="font-medium">{i.mall}</span>{i.mall_kind === 'official' && <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600" title={t("제조사 공식몰의 할인 전 판매가입니다. 카드·쿠폰 혜택가는 공식몰에서 확인하세요.")}>{t("공식몰 정가")}</span>}{i.is_lowest && <span className="ml-2 text-[11px] text-emerald-700">{t("최저")}</span>}{!i.in_stock && <span className="ml-2 text-xs text-slate-500">{t("품절")}</span>}
        {!compact && <MallStats item={i} />}</td>
      {!compact && <><td className="numeric whitespace-nowrap text-right">{won(i.price)}</td><td className="whitespace-nowrap text-right">{i.shipping_fee ? won(i.shipping_fee) : t("무료")}</td></>}
      <td className={`numeric whitespace-nowrap text-right ${i.is_lowest ? 'text-emerald-700' : ''}`}>{won(i.total_price)}</td>
      {!compact && <td>{i.in_stock && safeUrl(i.url) ? <a href={i.url} className="btn-outline px-3" target="_blank" rel="noopener noreferrer" aria-label={t("{x} 구매 페이지 새 창", { x: i.mall })}>{t("구매하기")}<Icon name="arrow-up-right-from-square" /></a> : '—'}</td>}</tr>)}</tbody></table></div>;
}
function MallStats({ item }) {
  // 가격 비교 사이트가 집계한 값(다나와·에누리): 입점 판매처 수 · 최고가 · 평점. 직접 판매처는 값이 없어 표시하지 않는다
  const parts = [item.offer_count > 0 && t("판매처 {n}곳", { n: item.offer_count.toLocaleString('ko-KR') }),
    item.high_price > 0 && t("최고 {x}", { x: won(item.high_price) }),
    item.rating > 0 && `★ ${item.rating.toFixed(1)}${item.review_count ? ` (${t("리뷰 {n}", { n: item.review_count.toLocaleString('ko-KR') })})` : ''}`].filter(Boolean);
  return parts.length ? <p className="mt-0.5 text-[11px] text-slate-500">{parts.join(' · ')}</p> : null;
}
function PriceSpotlight({ product }) {
  const { user } = useAuth();
  const history = useApi(user && product ? `/products/${product.id}/prices?days=90` : null);
  const comparison = useApi(user && product ? `/products/${product.id}/compare` : null);
  if (!product) return <div className="flex min-h-64 flex-col items-center justify-center gap-4 rounded-2xl border border-white bg-white/70 text-slate-500"><Icon name="chart-line" className="text-4xl text-brand-500" /><p className="text-sm">{t("수집한 가격이 쌓이면 구매 타이밍이 보입니다.")}</p></div>;
  return <div className="min-w-0 rounded-2xl border border-slate-200/70 bg-white p-5 shadow-[0_12px_40px_-20px_#53607955] sm:p-6">
    <div className="flex items-center justify-between gap-3"><span className="inline-flex items-center gap-2 text-xs text-slate-500"><span className="size-1.5 rounded-full bg-emerald-500" />{t("오늘의 타이밍 분석")}</span><span className="text-[11px] text-slate-500">{t("최근 90일 기준")}</span></div>
    <div className="mt-5 flex items-center gap-4"><div className="w-16 shrink-0 overflow-hidden rounded-xl"><Photo product={product} caption={false} /></div><div className="min-w-0"><Link to={`/product/${product.id}`} className="font-display text-base font-medium hover:text-brand-700">{product.name}</Link><div className="numeric mt-1 text-2xl">{won(priceOf(product))}</div></div></div>
    <div className="mt-5"><TimingGauge timing={product} compact /></div>
    {user ? <>{history.loading ? <Loading text={t("가격 흐름 확인 중")} /> : history.error ? <Notice error={history.error} /> : history.data && <div className="my-3"><PriceChart data={history.data} mini /></div>}{comparison.data && <CompareTable data={comparison.data} compact />}</>
      : <div className="mt-5 flex items-center justify-between gap-2 border-t border-slate-100 pt-4 text-sm"><p className="text-slate-500">{t("90일 추이와 판매처 비교까지")}</p><Link to={`/login?next=/product/${product.id}`} className="text-brand-700">{t("로그인해서 확인")}</Link></div>}</div>;
}
function Home() {
  const [params] = useSearchParams(); const [view, setView] = useState(params.get('view') === 'drops' ? 'drops' : 'timing');
  const [category, setCategory] = useState('전체'); const [version, setVersion] = useState(0); const deals = useApi('/deals/today', version);
  useEffect(() => { if (params.get('view')) setView(params.get('view') === 'drops' ? 'drops' : 'timing'); }, [params]);
  const items = (deals.data?.[view] || []).filter((p) => (category === '전체' || p.category === category) && (view !== 'drops' || p.change_7d < 0));
  return <>
    <section className="hero-surface border-b border-slate-200/50"><div className="container-x grid grid-cols-1 items-center gap-10 py-12 lg:grid-cols-[1.1fr_1fr] lg:gap-16 lg:py-16">
      <div><div className="mb-6 inline-flex items-center gap-2 rounded-full border border-brand-100 bg-white/70 px-3 py-1.5 text-xs text-brand-700"><Icon name="chart-line" />{t("가격 비교, 그 다음의 선택")}</div>
        <h1 className="whitespace-pre-line text-[38px] leading-[1.35] tracking-[-0.04em] sm:text-[48px]">{t("가격을 비교하고,\n살 때를 발견하세요.")}</h1>
        <p className="mt-5 max-w-md text-[15px] leading-7 text-slate-600">{t("지금 가격이 정말 괜찮은지 고민하지 마세요.")}<br className="hidden sm:block" />{t("가격의 흐름을 읽고, 나에게 맞는 구매 시점을 찾으세요.")}</p>
        <div className="mt-7"><SearchBar name={t("메인 상품 검색")} large /></div>
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs"><span className="text-slate-500">{t("추천 검색")}</span>{['이어폰', '공기청정기', '삼다수'].map((q) => <Link key={q} to={`/search?q=${encodeURIComponent(q)}`} className="py-2 text-slate-600 hover:text-brand-700">{t(q)}</Link>)}</div>
        <div className="mt-8 flex flex-wrap gap-5 border-t border-slate-200/70 pt-5 text-xs text-slate-500"><span><Icon name="clock" className="mr-1.5 text-brand-600" />{t("하루 4회 가격 수집")}</span><span><Icon name="truck-fast" className="mr-1.5 text-brand-600" />{t("배송비 포함 비교")}</span><span><Icon name="shield-halved" className="mr-1.5 text-brand-600" />{t("데이터 기반 판단")}</span></div></div>
      <PriceSpotlight product={deals.data?.timing?.[0]} />
    </div></section>
    <section className="container-x pt-10"><div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">{CATEGORIES.map((c) => <Link key={c.name} to={`/search?category=${encodeURIComponent(c.name)}`} className="group flex items-center gap-3 rounded-xl border border-slate-200 p-3 hover:border-brand-500">
      <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-slate-50 text-xl text-slate-500 group-hover:bg-brand-50 group-hover:text-brand-600"><Icon name={c.icon} /></span><span><span className="text-sm font-medium">{t(c.name)}</span><span className="mt-1 block text-[11px] text-slate-500">{c.caption}</span></span></Link>)}</div></section>
    <section className="container-x pt-14" id="discover"><div className="flex flex-wrap items-end justify-between gap-4"><div><h2 className="section-title">{t("오늘, 눈여겨볼 가격")}</h2><p className="section-note">{t("지금 구매하기 좋은 상품과 최근 가격이 내려간 상품을 모았어요.")}</p></div><Link to="/search" className="btn-ghost">{t("모든 상품 보기")}<Icon name="arrow-right" /></Link></div>
      <div className="mt-7 flex flex-wrap justify-between gap-4 border-b border-slate-200"><div className="flex gap-6" aria-label={t("추천 기준")}>{[['timing', t("구매 타이밍 추천")], ['drops', t("7일 가격 하락")]].map(([key, text]) => <button key={key} aria-pressed={view === key} onClick={() => setView(key)} className={`min-h-12 border-b-2 pb-3 text-sm ${view === key ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'}`}>{text}</button>)}</div>
        <label className="flex items-center gap-2 pb-2 text-xs text-slate-500"><Icon name="filter" className="text-slate-400" />{t("카테고리")}<select className="select-x" value={category} onChange={(e) => setCategory(e.target.value)}><option>{t("전체")}</option>{CATEGORIES.map((c) => <option key={c.name}>{t(c.name)}</option>)}</select></label></div>
      <div className="mt-6">{deals.loading ? <Loading /> : deals.error ? <Notice error={deals.error} retry={() => setVersion((v) => v + 1)} /> : items.length ? <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">{items.map((p) => <ProductCard key={p.id} product={p} />)}</div>
      : <Empty title="이 조건의 추천 상품이 아직 없어요"><button onClick={() => setCategory('전체')} className="btn-ghost text-brand-700">{t("전체 카테고리 보기")}</button><p>{t("새 가격이 수집되면 추천에 반영됩니다.")}</p></Empty>}</div>
      <div className="mt-5 flex justify-end"><button className="btn-ghost text-xs" onClick={() => setVersion((v) => v + 1)} disabled={deals.loading}><Icon name="rotate" />{t("추천 새로고침")}</button></div></section>
    <section className="container-x mt-14"><div className="flex flex-wrap items-center justify-between gap-6 rounded-2xl bg-brand-50 px-6 py-8 sm:px-10">
      <div className="flex items-center gap-5"><span className="hidden size-14 items-center justify-center rounded-2xl bg-white text-2xl text-brand-600 sm:flex"><Icon name="bell" /></span><div><h2 className="text-xl">{t("가격을 기다리는 일은 맡겨두세요.")}</h2><p className="mt-2 text-sm text-slate-500">{t("원하는 가격에 도달하면 내 알림에서 확인할 수 있어요.")}</p></div></div>
      <Link className="btn-primary" to="/watchlist">{t("내 가격 알림 관리")}<Icon name="arrow-right" /></Link></div></section>
  </>;
}

function Explore() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const q = params.get('q') || ''; const category = params.get('category') || '전체';
  const [sort, setSort] = useState('score'); const [onlyBuy, setOnlyBuy] = useState(false);
  const [personalOnly, setPersonalOnly] = useState(false);
  let interests = [];
  try {
    const saved = JSON.parse(localStorage.getItem(`pt_interests_${user?.id}`) || '[]');
    if (Array.isArray(saved)) interests = saved.filter((s) => CATEGORIES.some((c) => c.name === s));
  } catch { /* 저장된 취향이 손상되면 전체 상품 탐색을 제공한다. */ }
  const [version, setVersion] = useState(0); const [register, setRegister] = useState(false);
  // 분류·정렬·필터는 서버가 전체 상품에 적용하고 PAGE_SIZE씩 나눠 준다(상품이 늘어도 빠지는 상품이 없게)
  const page = Math.max(1, Number(params.get('page')) || 1);
  const cats = personalOnly ? (category === '전체' ? interests : interests.filter((c) => c === category)) : (category === '전체' ? [] : [category]);
  const query = new URLSearchParams({ q, sort, page: String(page), size: String(PAGE_SIZE), ...(cats.length ? { category: cats.join(',') } : {}), ...(onlyBuy ? { buy_only: 'true' } : {}) });
  const noMatch = personalOnly && !cats.length;
  const result = useApi(noMatch ? null : `/products/search?${query}`, version);
  const items = noMatch ? [] : result.data?.items || [];
  const total = noMatch ? 0 : result.data?.total ?? items.length; const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const goPage = (n) => { setParams({ ...(q ? { q } : {}), ...(category !== '전체' ? { category } : {}), ...(n > 1 ? { page: String(n) } : {}) }); window.scrollTo({ top: 0 }); };
  const resetPage = (fn) => (e) => { fn(e); if (page > 1) goPage(1); };
  return <div className="container-x py-10">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="section-title">{t("상품 탐색")}</h1><p className="section-note">{t("같은 상품, 다른 가격. 배송비까지 비교하고 구매 시점을 살펴보세요.")}</p></div>
      <button className="btn-outline" onClick={() => setRegister(true)}><Icon name="link" />{t("상품 URL 등록")}</button></div>
    <div className="mt-7 max-w-2xl"><SearchBar name={t("결과 내 상품 검색")} initial={q} large /></div>
    <div className="mt-6 flex flex-wrap gap-2" aria-label="검색 카테고리">{['전체', ...CATEGORIES.map((c) => c.name)].map((c) => <button key={c} className="filter-chip" aria-pressed={category === c}
      onClick={() => setParams({ ...(q ? { q } : {}), ...(c !== '전체' ? { category: c } : {}) })}>{t(c)}</button>)}</div>
    <div className="my-6 flex flex-wrap items-center justify-between gap-4 border-y border-slate-200 py-4">
      <p className="text-sm text-slate-600">{q && <span className="text-slate-900">‘{q}’ </span>}{t("검색 결과")}{" "}<span className="numeric text-brand-700">{total}</span>{t("개")}</p>
      <div className="flex flex-wrap items-center gap-4 text-sm"><label className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={onlyBuy} onChange={resetPage((e) => setOnlyBuy(e.target.checked))} />{t("지금 구매 추천만")}</label>
        {!!interests.length && <label className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={personalOnly} onChange={resetPage((e) => setPersonalOnly(e.target.checked))} />{t("내 관심 카테고리")}</label>}
        <select aria-label={t("상품 정렬")} className="select-x min-h-11" value={sort} onChange={resetPage((e) => setSort(e.target.value))}><option value="score">{t("적기 점수순")}</option><option value="price">{t("낮은 가격순")}</option></select></div></div>
    {result.loading ? <Loading /> : result.error ? <Notice error={result.error} retry={() => setVersion((v) => v + 1)} /> : items.length
      ? <><div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{items.map((p) => <ProductCard key={p.id} product={p} />)}</div>
        {pages > 1 && <nav className="mt-8 flex items-center justify-center gap-2" aria-label={t("검색 결과 페이지")}>
          <button className="btn-outline" disabled={page <= 1} onClick={() => goPage(page - 1)}>{t("이전")}</button>
          <span className="numeric px-2 text-sm" aria-current="page">{page} / {pages}</span>
          <button className="btn-outline" disabled={page >= pages} onClick={() => goPage(page + 1)}>{t("다음")}</button></nav>}</>
      : <Empty title={t("조건에 맞는 상품이 없어요")}><p>{t("다른 검색어나 카테고리를 선택해 보세요.")}</p><button className="btn-outline mt-4" onClick={() => { setParams({}); setOnlyBuy(false); setPersonalOnly(false); }}>{t("검색 조건 초기화")}</button></Empty>}
    <RegisterProduct open={register} onClose={() => setRegister(false)} onSaved={() => setVersion((v) => v + 1)} />
  </div>;
}
function RegisterProduct({ open, onClose, onSaved }) {
  const [url, setUrl] = useState(''); const [name, setName] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState(null);
  const toast = useToast();
  async function submit(e) {
    e.preventDefault(); if (busy) return;
    if (!safeUrl(url.trim())) return setError(new Error(t("http 또는 https 상품 주소를 입력하세요.")));
    setBusy(true); setError(null);
    try { const r = await api.post('/products', { url: url.trim(), name: name.trim() || null }); toast(r.message, 'success'); setUrl(''); setName(''); onSaved(); onClose(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  }
  return <Dialog open={open} title={t("상품 URL 등록")} onClose={onClose}><p className="mb-5 text-sm leading-6 text-slate-500">{t("수집이 허용된 판매처의 상품을 등록하면 다음 수집부터 가격을 확인할 수 있어요.")}</p>
    <form onSubmit={submit} className="space-y-4"><Field label={t("상품 URL")} icon="link" type="url" required maxLength={500} value={url} onChange={(e) => setUrl(e.target.value)} />
      <Field label={t("상품 이름 (선택)")} icon="box" maxLength={200} value={name} onChange={(e) => setName(e.target.value)} /><Notice error={error} />
      <button disabled={busy} className="btn-primary w-full">{busy ? t("등록 중…") : t("상품 등록")}</button></form></Dialog>;
}
function WatchDialog({ selection, onClose, onSaved }) {
  const p = selection.product; const existing = selection.watch;
  const [target, setTarget] = useState(existing?.target_price ?? (priceOf(p) > 0 ? Math.round(priceOf(p) * 0.95 / 100) * 100 : ''));
  const [busy, setBusy] = useState(false); const [error, setError] = useState(null); const [saved, setSaved] = useState(false);
  async function submit(e) {
    e.preventDefault(); if (busy) return;
    const amount = Number(target);
    if (!Number.isSafeInteger(amount) || amount <= 0 || amount > 2_000_000_000) return setError(new Error(t("목표가는 1원 이상 20억 원 이하의 정수로 입력하세요.")));
    setBusy(true); setError(null);
    try {
      // 카드에서 다시 설정해도 기존 관심 상품을 찾아 목표가를 갱신한다.
      const watch = existing || (await api.get('/watchlist')).items.find((w) => w.product.id === p.id);
      if (watch) await api.patch(`/watchlist/${watch.id}`, { target_price: amount });
      else await api.post('/watchlist', { product_id: p.id, target_price: amount });
      setSaved(true); onSaved();
    } catch (err) { setError(err); } finally { setBusy(false); }
  }
  return <Dialog open title={t("목표가 알림")} onClose={onClose}>
    {saved ? <div className="text-center"><span className="mx-auto mb-4 flex size-16 items-center justify-center rounded-full bg-emerald-50 text-2xl text-emerald-600"><Icon name="check" /></span>
      <h3 className="text-xl">{t("목표가 알림이 저장되었습니다.")}</h3><p className="mt-3 text-sm leading-6 text-slate-500">{p.name}<br />{won(Number(target))}{" "}{t("이하로 수집되면 내 알림에서 알려드려요.")}</p>
      <button autoFocus className="btn-primary mt-6 w-full" onClick={onClose}>{t("확인")}</button></div>
      : <form onSubmit={submit}><div className="mb-6 flex items-center gap-4"><div className="w-20 overflow-hidden rounded-xl"><Photo product={p} /></div><div className="min-w-0"><p className="text-sm font-medium">{p.name}</p><p className="mt-1 text-xs text-slate-500">{t("현재 최저 실구매가")}</p><p className="numeric text-lg">{won(priceOf(p))}</p></div></div>
        <Field label={t("목표 가격 (원)")} icon="won-sign" type="number" min="1" max="2000000000" step="1" required value={target} onChange={(e) => setTarget(e.target.value)} />
        {priceOf(p) > 0 && <div className="mt-3 flex flex-wrap gap-2">{[5, 10, 15].map((discount) => <button type="button" key={discount} className="filter-chip px-3 text-xs" onClick={() => setTarget(Math.max(1, Math.round(priceOf(p) * (1 - discount / 100) / 100) * 100))}>{discount}{t("% 더 저렴하게")}</button>)}</div>}
        <p className="mt-5 rounded-xl bg-slate-50 p-4 text-xs leading-6 text-slate-500"><Icon name="circle-info" className="mr-1" />{t("알림은 사이트 안의 ‘가격 알림’에 표시됩니다. 이메일·문자·브라우저 푸시는 발송하지 않습니다.")}</p>
        <Notice error={error} /><button className="btn-primary mt-5 w-full" disabled={busy}><Icon name={busy ? 'circle-notch' : 'bell'} className={busy ? 'animate-spin' : ''} />{busy ? t("저장 중…") : t("알림 저장")}</button>
      </form>}
  </Dialog>;
}
function ProductDetail() {
  const { id } = useParams(); const { openWatch } = useContext(UIContext);
  const [days, setDays] = useState(90); const [tab, setTab] = useState('compare'); const [version, setVersion] = useState(0);
  const product = useApi(`/products/${id}`, version); const timing = useApi(`/products/${id}/timing`, version);
  const compare = useApi(`/products/${id}/compare`, version); const history = useApi(`/products/${id}/prices?days=${days}`, version);
  const [advice, setAdvice] = useState(null); const [adviceError, setAdviceError] = useState(null); const [asking, setAsking] = useState(false);
  useEffect(() => { setAdvice(null); setAdviceError(null); setDays(90); setTab('compare'); }, [id]);
  useEffect(() => { if (product.data) document.title = `${product.data.name} · ${t("타임픽")}`; }, [product.data]);
  async function requestAdvice() {
    if (asking) return; setAsking(true); setAdviceError(null);
    try { setAdvice(await api.post(`/products/${id}/advice`)); } catch (err) { setAdviceError(err); } finally { setAsking(false); }
  }
  if (product.loading) return <Loading />;
  if (product.error) return <div className="container-x py-8"><Notice error={product.error} retry={() => setVersion((v) => v + 1)} /></div>;
  const p = { ...product.data, ...timing.data, id: Number(id) };
  const atLow = p.current_price > 0 && history.data?.all_time_min?.price > 0 && p.current_price <= history.data.all_time_min.price && (p.history_days || 0) >= MIN_LOW_DAYS;
  return <div className="container-x py-8">
    <nav aria-label={t("현재 위치")} className="mb-6 flex gap-2 text-xs text-slate-500"><Link to="/search">{t("상품 탐색")}</Link><span>/</span><span>{t(p.category)}</span></nav>
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_1.3fr]">
      <div className="overflow-hidden rounded-3xl"><Photo product={p} /></div>
      <section className="flex flex-col justify-center"><p className="text-sm text-slate-500">{p.brand} · {p.model_no}</p><h1 className="mt-2 text-3xl leading-snug sm:text-4xl">{p.name}</h1>
        <div className="mt-4 flex flex-wrap gap-2"><Signal product={p} />{atLow && <span className="badge bg-emerald-600 text-white"><Icon name="medal" />{t("역대 최저가")}</span>}</div>
        {p.spec_summary && <div className="mt-5"><p className="text-xs text-slate-500">{t("주요 사양")}</p>
          <ul className="mt-2 flex flex-wrap gap-1.5" aria-label={t("주요 사양")}>{p.spec_summary.split(' / ').filter(Boolean).slice(0, 12).map((s, n) => <li key={n} className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">{s}</li>)}</ul></div>}
        <p className="mt-7 text-xs text-slate-500">{t("배송비 포함 현재 최저가")}</p><p className="numeric mt-1 text-4xl">{won(p.current_price ?? compare.data?.lowest_total)}</p>
        <div className="mt-5 flex flex-wrap gap-8 text-sm"><div><p className="text-slate-500">{t("기록된 역대 최저가")}</p><p className="numeric mt-1 text-emerald-700">{won(history.data?.all_time_min?.price)}</p></div><div><p className="text-slate-500">{t("최근 수집")}</p><p className="mt-1 text-xs">{dateText(compare.data?.collected_at)}</p></div>
          {p.offline_price && <div><p className="text-slate-500">{t("오프라인 최저가 (참가격)")}</p><p className="numeric mt-1">{won(p.offline_price.price)}</p>
            <p className="mt-0.5 text-[11px] text-slate-500">{[p.offline_price.store_type, t("{d} 조사", { d: p.offline_price.survey_date })].filter(Boolean).join(' · ')}</p></div>}</div>
        <div className="mt-7 flex flex-wrap gap-3"><button className="btn-primary flex-1" onClick={() => openWatch(p)}><Icon name="bell" />{t("목표가 알림")}</button><Link to={`/chat/${id}`} className="btn-outline flex-1"><Icon name="wand-magic-sparkles" />{t("AI와 상담하기")}</Link></div>
      </section>
    </div>
    <div className="mt-12 grid grid-cols-1 items-start gap-7 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0">
        <section className="card p-5 sm:p-7"><div className="mb-5 flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl">{t("가격의 흐름")}</h2><div className="inline-flex rounded-xl bg-slate-100 p-1" aria-label={t("가격 조회 기간")}>{[7, 30, 90].map((n) => <button key={n} onClick={() => setDays(n)} aria-pressed={days === n} className={`min-h-10 rounded-lg px-4 text-xs ${days === n ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500'}`}>{n}{t("일")}</button>)}</div></div>
          {history.loading ? <Loading /> : history.error ? <Notice error={history.error} /> : <PriceChart key={`${id}-${days}`} data={history.data} />}
          <p className="mt-2 text-[11px] text-slate-500">{t("판매처별 일간 최저 실구매가 · 아래 막대로 날짜별 가격을 확인하세요.")}</p>
        </section>
        <div className="mt-8 flex gap-6 border-b border-slate-200">{[['compare', t("판매처 비교")], ['analysis', t("AI 구매 조언")]].map(([value, text]) => <button className={`min-h-12 border-b-2 text-sm ${tab === value ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'}`} aria-pressed={tab === value} key={value} onClick={() => setTab(value)}>{text}</button>)}</div>
        {tab === 'compare' ? <section className="mt-6"><h2 className="mb-4 text-xl">{t("쇼핑몰별 실구매가")}</h2>{compare.loading ? <Loading /> : compare.error ? <Notice error={compare.error} /> : <div className="card overflow-hidden"><CompareTable data={compare.data} /></div>}</section>
          : <section className="mt-6 card p-6"><h2 className="text-xl"><Icon name="wand-magic-sparkles" className="mr-2 text-brand-600" />{t("내 구매를 위한 한 줄 조언")}</h2>
            {advice ? <><span className="badge mt-4 bg-brand-50 text-brand-700">{advice.source === 'gemini' ? 'Gemini' : t("규칙 기반 분석")}{advice.cached && t(" · 저장된 분석")}</span><h3 className="mt-4 text-lg">{advice.verdict}</h3><p className="mt-3 text-sm leading-7 text-slate-600">{advice.summary}</p><ul className="mt-4 space-y-3">{advice.reasons.map((r) => <li key={r} className="flex gap-2 text-sm"><Icon name="check" className="mt-1 text-emerald-600" />{r}</li>)}</ul><p className="mt-4 text-xs text-slate-500">{advice.caution}{advice.remaining != null && t(" · 오늘 {n}회 남음", { n: advice.remaining })}</p></>
              : <><p className="mt-3 text-sm leading-7 text-slate-500">{t("가격 이력과 적기 점수를 바탕으로 지금 사도 괜찮은지 설명해 드립니다. 분석 요청 시 일일 사용량이 차감될 수 있습니다.")}</p><button className="btn-primary mt-4" disabled={asking} onClick={requestAdvice}>{asking ? t("분석 중…") : t("구매 조언 받기")}</button></>}<Notice error={adviceError} /></section>}
      </div>
      <aside className="card p-6"><h2 className="mb-5 text-lg">{t("구매 타이밍 신호등")}</h2>{timing.loading ? <Loading /> : timing.error ? <Notice error={timing.error} /> : <TimingGauge timing={p} />}
        <dl className="mt-6 space-y-4 text-sm">{[[t("90일 최저가"), won(p.min_90d)], [t("7일 내 5% 하락 확률"), percent(p.prob_drop_7d)], [t("분석한 가격 이력"), t("{n}일", { n: p.history_days ?? '—' })]].map(([k, v]) => <div className="flex justify-between gap-3" key={k}><dt className="text-slate-500">{k}</dt><dd className="numeric">{v}</dd></div>)}</dl>
        <Link to="/guide" className="mt-6 inline-flex min-h-11 items-center gap-2 text-xs text-brand-700">{t("추천은 어떻게 만들어지나요?")}<Icon name="angle-right" /></Link>
      </aside>
    </div>
  </div>;
}
function Watchlist() {
  const { revision, refresh, openWatch } = useContext(UIContext); const toast = useToast();
  const result = useApi('/watchlist', revision); const [removing, setRemoving] = useState(null); const [busy, setBusy] = useState(false);
  async function remove() {
    if (busy) return; setBusy(true);
    try { await api.del(`/watchlist/${removing.id}`); refresh(); setRemoving(null); toast(t("관심 상품을 삭제했습니다.")); } catch (err) { toast(err.message, 'danger'); } finally { setBusy(false); }
  }
  return <div className="container-x py-10"><h1 className="section-title">{t("내 관심 상품")}</h1><p className="section-note">{t("좋은 가격을 기다리는 나만의 목록. 목표가를 정해두면 더 편해요.")}</p>
    <div className="mt-8">{result.loading ? <Loading /> : result.error ? <Notice error={result.error} retry={refresh} /> : !result.data.items.length ? <Empty title={t("기다리는 상품을 담아보세요")} icon="heart"><Link to="/search" className="btn-primary mt-4">{t("상품 둘러보기")}</Link></Empty>
      : <div className="grid gap-4">{result.data.items.map((w) => <article key={w.id} className="card flex flex-wrap items-center gap-5 p-5">
        <div className="w-24 shrink-0 overflow-hidden rounded-xl"><Photo product={w.product} /></div>
        <div className="min-w-0 flex-1"><Link className="font-display font-medium hover:text-brand-700" to={`/product/${w.product.id}`}>{w.product.name}</Link><p className="mt-2 text-xs text-slate-500">{t(w.product.category)}</p><div className="mt-2"><Signal product={w} /></div></div>
        <div className="min-w-28"><p className="text-xs text-slate-500">{t("현재 최저가")}</p><p className="numeric mt-1 text-lg">{won(w.current_price)}</p></div>
        <div className="min-w-28"><p className="text-xs text-slate-500">{t("내 목표가")}{" "}{w.reached && <span className="text-emerald-700">{t("도달!")}</span>}</p><p className="numeric mt-1 text-lg">{w.target_price ? won(w.target_price) : t("설정 안 함")}</p></div>
        <div className="flex gap-2"><button className="btn-outline" onClick={() => openWatch({ ...w.product, current_price: w.current_price }, w)}>{t("목표가 변경")}</button><button className="icon-btn text-rose-600" onClick={() => setRemoving(w)} aria-label={t("{x} 관심 삭제", { x: w.product.name })}><Icon name="trash-can" /></button></div>
      </article>)}</div>}</div>
    <Dialog open={!!removing} title={t("관심 상품 삭제")} onClose={() => setRemoving(null)}><p className="text-sm leading-7">{removing?.product.name}{t("의 관심 등록과 목표가 알림 설정을 삭제할까요?")}</p>
      <div className="mt-6 flex gap-3"><button className="btn-outline flex-1" onClick={() => setRemoving(null)}>{t("취소")}</button><button className="btn flex-1 bg-rose-600 text-white" onClick={remove} disabled={busy}>{t("삭제")}</button></div></Dialog>
  </div>;
}
function Alerts() {
  const { revision, refresh } = useContext(UIContext); const result = useApi('/alerts', revision); const toast = useToast();
  const [unreadOnly, setUnreadOnly] = useState(false); const [busy, setBusy] = useState(false);
  async function readAll() { setBusy(true); try { await api.post('/alerts/read-all'); refresh(); } catch (err) { toast(err.message, 'danger'); } finally { setBusy(false); } }
  const items = result.data?.items.filter((a) => !unreadOnly || !a.is_read) || [];
  return <div className="container-x max-w-4xl py-10"><div className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="section-title">{t("가격 알림")}</h1><p className="section-note">{t("기다리던 가격과 구매 타이밍의 변화.")}</p></div><button className="btn-outline" disabled={busy || !result.data?.unread} onClick={readAll}><Icon name="check-double" />{t("모두 읽음")}</button></div>
    <label className="my-6 flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />{t("읽지 않은 알림만")}</label>
    {result.loading ? <Loading /> : result.error ? <Notice error={result.error} retry={refresh} /> : !items.length ? <Empty title={t("새로운 가격 소식을 기다리는 중이에요")} icon="bell"><Link to="/watchlist" className="btn-ghost text-brand-700">{t("목표가 설정 확인하기")}</Link></Empty>
      : <div className="card divide-y divide-slate-100">{items.map((a) => <Link key={a.id} to={`/product/${a.product_id}`} className="flex gap-4 p-5 hover:bg-slate-50"><span className={`flex size-11 shrink-0 items-center justify-center rounded-xl ${a.is_read ? 'bg-slate-100 text-slate-500' : 'bg-emerald-50 text-emerald-600'}`}><Icon name={a.type === 'TARGET_PRICE' ? 'bullseye' : 'chart-line'} /></span><div className="flex-1"><p className={`text-sm leading-6 ${a.is_read ? 'text-slate-500' : 'text-slate-900'}`}>{a.message}</p><p className="mt-2 text-xs text-slate-500">{dateText(a.created_at)}</p></div>{!a.is_read && <span className="mt-2 size-2 rounded-full bg-brand-500" aria-label={t("읽지 않음")} />}</Link>)}</div>}
  </div>;
}

function Field({ label, icon, hint, ...props }) {
  const id = useId();
  return <div><label htmlFor={id} className="mb-2 block text-sm font-medium">{label}</label>
    <div className="relative"><span className="field-icon"><Icon name={icon} /></span><input id={id} className="input field-with-icon" aria-describedby={hint ? `${id}-hint` : undefined} {...props} /></div>
    {hint && <p id={`${id}-hint`} className="mt-2 text-xs text-slate-500">{hint}</p>}</div>;
}
function AuthStory() {
  return <aside className="hero-surface hidden flex-col justify-between rounded-3xl p-10 lg:flex">
    <div><span className="badge bg-white text-brand-700"><Icon name="clock" />{t("쇼핑에도 좋은 타이밍이 있으니까")}</span>
      <h2 className="mt-8 text-4xl leading-snug">{t("좋은 선택은")}<br />{t("좋은 정보에서.")}</h2><p className="mt-4 text-sm leading-7 text-slate-600">{t("비교하고, 기다리고, 발견하는 즐거움.")}<br />{t("내가 원하는 가격으로 쇼핑을 시작하세요.")}</p></div>
    <div className="my-8 overflow-hidden rounded-2xl"><img src={photoUrl('photo-1505740420928-5e560c06d30e')} alt={t("음악 감상용 헤드폰 참고 이미지")} width="700" height="450" className="aspect-[4/3] w-full object-cover" /></div>
    <ul className="space-y-4 text-sm text-slate-600">{[['chart-line', t("90일 흐름으로 판단하는 구매 타이밍")], ['bell', t("내 목표가에 맞춘 가격 알림")], ['scale-balanced', t("배송비를 포함한 실구매가 비교")]].map(([icon, text]) => <li className="flex gap-3" key={icon}><Icon name={icon} className="mt-1 text-brand-600" />{text}</li>)}</ul>
  </aside>;
}
function Login() {
  const { login, demoLogin } = useAuth(); const nav = useNavigate(); const [params] = useSearchParams();
  const next = safeNext(params.get('next')); const providers = useApi('/auth/providers');
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [error, setError] = useState(params.get('oauth_error') ? new Error(params.get('oauth_error')) : null); const [busy, setBusy] = useState(false);
  async function run(fn) { if (busy) return; setBusy(true); setError(null); try { await fn(); nav(next, { replace: true }); } catch (err) { setError(err); } finally { setBusy(false); } }
  return <div className="container-x grid grid-cols-1 gap-10 py-10 lg:grid-cols-2">
    <AuthStory /><section className="mx-auto flex w-full max-w-md flex-col justify-center py-6"><h1 className="text-3xl">{t("다시 만나 반가워요.")}</h1><p className="section-note">{t("관심 상품의 가격은 어떻게 달라졌을까요?")}</p>
      <form className="mt-8 space-y-5" onSubmit={(e) => { e.preventDefault(); run(() => login(email.trim(), password)); }}>
        <Field label={t("이메일")} icon="envelope" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label={t("비밀번호")} icon="lock" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        <Notice error={error} /><button className="btn-primary w-full" disabled={busy}>{busy ? t("로그인 중…") : t("로그인")}<Icon name="arrow-right" /></button></form>
      <p className="mt-5 text-center text-sm text-slate-500">{t("아직 회원이 아니신가요?")}{" "}<Link to="/signup" className="ml-2 text-brand-700 underline underline-offset-4">{t("회원가입")}</Link></p>
      <div className="my-7 flex items-center gap-4 text-xs text-slate-500"><span className="h-px flex-1 bg-slate-200" />{t("소셜 계정으로 간편하게")}<span className="h-px flex-1 bg-slate-200" /></div>
      <div className="grid grid-cols-3 gap-3">{[['google', 'Google', 'fa-brands fa-google', 'bg-white'], ['naver', t("네이버"), 'fa-solid fa-n', 'bg-emerald-50'], ['kakao', t("카카오"), 'fa-solid fa-comment', 'bg-yellow-100']].map(([key, name, icon, bg]) =>
        <button key={key} disabled={busy || !providers.data?.[key]} className={`btn-outline flex-col gap-1 py-3 ${bg}`} title={providers.data?.[key] ? t("{x} 로그인", { x: name }) : t("아직 연결되지 않은 로그인 방식")}
          onClick={() => { window.location.assign(oauthStartUrl(key, next)); }}><i className={icon} aria-hidden="true" />{name}<span className="text-[10px] text-slate-500">{providers.data?.[key] ? t("로그인") : t("준비 중")}</span></button>)}</div>
      <Notice error={providers.error} />
      {providers.data?.demo_login && <div className="mt-7 rounded-2xl border border-dashed border-slate-300 p-4"><p className="mb-3 text-xs text-slate-500">{t("테스트 계정 · 가입 전에 둘러보세요. 테스트 관리자는 조회 전용이며, 실제 관리자는 위 이메일·비밀번호로 로그인합니다.")}</p>
        <div className="grid grid-cols-2 gap-2"><button className="btn-ghost bg-slate-50 text-xs" disabled={busy} onClick={() => run(() => demoLogin('user'))}><Icon name="user" />{t("일반 사용자 테스트")}</button>
          <button className="btn-ghost bg-slate-50 text-xs" disabled={busy} onClick={() => run(() => demoLogin('admin'))}><Icon name="user-shield" />{t("관리자 테스트")}</button></div></div>}
    </section></div>;
}

function Signup() {
  const { login } = useAuth(); const { openWatch } = useContext(UIContext); const toast = useToast();
  const [step, setStep] = useState(1); const [agreements, setAgreements] = useState({ terms: false, privacy: false });
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' }); const [categories, setCategories] = useState([]);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(null); const [created, setCreated] = useState(false); const [alertSaved, setAlertSaved] = useState(false);
  const recommendations = useApi(step === 3 ? `/products/search?sort=score&size=12${categories.length ? `&category=${encodeURIComponent(categories.join(','))}` : ''}` : null);
  const stepHeading = useRef(null);
  useEffect(() => { if (step > 1) stepHeading.current?.focus(); }, [step]);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const strength = PASSWORD_CHECKS.filter(([, test]) => test(form.password)).length;
  const valid = strength === PASSWORD_CHECKS.length && form.password === form.confirm;
  const picks = (recommendations.data?.items || []).filter((p) => !categories.length || categories.includes(p.category)).slice(0, 3);
  async function submit(e) {
    e.preventDefault(); if (busy || !valid || !agreements.terms || !agreements.privacy) return;
    if (!form.name.trim()) return setError(new Error(t("공백을 제외한 이름을 입력하세요.")));
    setBusy(true); setError(null);
    try {
      if (!created) { await api.post('/auth/signup', { name: form.name.trim(), email: form.email.trim(), password: form.password }); setCreated(true); }
      const newUser = await login(form.email.trim(), form.password);
      try { localStorage.setItem(`pt_interests_${newUser.id}`, JSON.stringify(categories)); }
      catch { toast(t("가입은 완료됐지만 이 브라우저에 관심 카테고리를 저장하지 못했습니다."), 'danger'); }
      setForm((f) => ({ ...f, password: '', confirm: '' })); setStep(3);
    } catch (err) { setError(err); } finally { setBusy(false); }
  }
  return <div className="container-x py-10">
    <div className="mx-auto max-w-3xl text-center"><h1 className="text-3xl">{t("나에게 맞는 쇼핑의 시작")}</h1><p className="section-note">{t("관심 있는 상품을 고르고, 원하는 가격을 기다려 보세요.")}</p></div>
    <ol className="mx-auto my-8 flex max-w-2xl items-center justify-between gap-2" aria-label={t("회원가입 단계")}>
      {[t("약관 동의"), t("계정과 관심 설정"), t("가입 완료")].map((label, i) => <li key={label} className="step-chip" aria-current={step === i + 1 ? 'step' : undefined}>
        <span>{step > i + 1 ? <Icon name="check" /> : i + 1}</span><span>{label}</span>{i < 2 && <span className="ml-2 hidden text-slate-300 sm:inline"><Icon name="angle-right" /></span>}</li>)}
    </ol>
    <div className={`mx-auto ${step === 3 ? 'max-w-5xl' : 'grid grid-cols-1 max-w-5xl gap-8 lg:grid-cols-[0.8fr_1fr]'}`}>
      {step < 3 && <AuthStory />}
      <section className={step === 3 ? 'card p-5 sm:p-8' : 'card p-6 sm:p-8'}>
        <h2 ref={stepHeading} tabIndex={-1} className="mb-2 text-2xl">{step === 1 ? t("먼저, 이용 안내를 확인해 주세요.") : step === 2 ? t("어떤 가격 소식이 궁금하세요?") : alertSaved ? t("가입과 알림 설정을 마쳤어요.") : t("첫 알림을 설정해 볼까요?")}</h2>
        {step === 1 && <>
          <p className="mb-6 text-sm leading-6 text-slate-500">{t("가입에 필요한 안내입니다. 내용을 펼쳐 확인할 수 있어요.")}</p>
          <label className="mb-5 flex min-h-12 items-center gap-3 border-b border-slate-200 pb-5 text-sm font-medium"><input type="checkbox" className="size-5" checked={agreements.terms && agreements.privacy} onChange={(e) => setAgreements({ terms: e.target.checked, privacy: e.target.checked })} />{t("필수 항목 전체 동의")}</label>
          {[['terms', t("서비스 이용 안내에 동의합니다 (필수)"), t("가격 비교와 구매 적기 분석은 참고 정보입니다. 실제 구매는 연결된 판매처에서 이루어지며 결제 금액과 재고는 판매처에서 확인해야 합니다.")],
            ['privacy', t("개인정보 처리 안내에 동의합니다 (필수)"), t("계정 생성에 이름, 이메일, 비밀번호를 사용합니다. 운영 서비스는 비밀번호를 해시로 저장하며, 관심 상품과 목표가를 계정에 연결합니다. 데모 공간은 브라우저 저장소에서 동작합니다.")]].map(([key, label, copy]) => <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50 p-4" key={key}>
              <label className="flex min-h-11 items-start gap-3 text-sm leading-6"><input type="checkbox" className="mt-1 size-4 shrink-0" checked={agreements[key]} onChange={(e) => setAgreements((a) => ({ ...a, [key]: e.target.checked }))} />{label}</label>
              <details className="mt-2 text-xs text-slate-500"><summary className="py-2">{t("안내 내용 펼치기")}</summary><p className="py-2 leading-6">{copy}</p><Link to={key === 'terms' ? '/terms' : '/privacy'} target="_blank" rel="noreferrer" className="inline-block py-2 text-brand-700">{t("전체 안내 새 창으로 보기")}</Link></details></div>)}
          <button className="btn-primary mt-4 w-full" disabled={!agreements.terms || !agreements.privacy} onClick={() => setStep(2)}>{t("동의하고 계속")}<Icon name="arrow-right" /></button>
          <p className="mt-5 text-center text-xs text-slate-500">{t("이미 계정이 있나요?")}{" "}<Link className="text-brand-700 underline underline-offset-4" to="/login">{t("로그인")}</Link></p>
        </>}
        {step === 2 && <form onSubmit={submit} className="mt-6 space-y-5">
          {created && <p role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800">{t("계정이 생성되었습니다. 로그인만 다시 시도하면 가입 단계를 마칠 수 있습니다.")}</p>}
          <Field label={t("이름")} icon="user" required maxLength={50} autoComplete="name" value={form.name} onChange={set('name')} readOnly={created} />
          <Field label={t("이메일")} icon="envelope" required type="email" maxLength={254} autoComplete="email" value={form.email} onChange={set('email')} readOnly={created} />
          <Field label={t("비밀번호")} icon="lock" required type="password" minLength={8} maxLength={72} autoComplete="new-password" value={form.password} onChange={set('password')} hint={t("영문 대·소문자, 숫자, 특수문자를 포함해 8~72자로 입력하세요.")} />
          <div><div className="flex gap-1" role="meter" aria-label={t("비밀번호 규칙 충족")} aria-valuemin={0} aria-valuemax={5} aria-valuenow={strength}>{PASSWORD_CHECKS.map(([label], i) => <span key={label} className={`h-1.5 flex-1 rounded-full ${i < strength ? 'bg-emerald-500' : 'bg-slate-200'}`} />)}</div>
            <ul className="mt-3 flex flex-wrap gap-x-3 gap-y-2 text-[11px]" aria-label={t("비밀번호 규칙")}>{PASSWORD_CHECKS.map(([label, check]) => <li key={label} className={check(form.password) ? 'text-emerald-700' : 'text-slate-500'}><Icon name={check(form.password) ? 'check' : 'minus'} className="mr-1" />{label}</li>)}</ul></div>
          <Field label={t("비밀번호 확인")} icon="shield-halved" required type="password" autoComplete="new-password" value={form.confirm} onChange={set('confirm')} aria-invalid={!!form.confirm && form.confirm !== form.password} hint={form.confirm && form.confirm !== form.password ? t("비밀번호가 일치하지 않습니다.") : undefined} />
          <fieldset><legend className="mb-3 text-sm font-medium">{t("관심 카테고리")}{" "}<span className="font-normal text-slate-500">{t("(선택)")}</span></legend>
            <div className="flex flex-wrap gap-2">{CATEGORIES.map((c) => <button type="button" key={c.name} aria-pressed={categories.includes(c.name)} className="filter-chip text-xs" onClick={() => setCategories((v) => v.includes(c.name) ? v.filter((s) => s !== c.name) : [...v, c.name])}><Icon name={c.icon} />{t(c.name)}</button>)}</div>
            <p className="mt-3 text-xs leading-6 text-slate-500">{t("이 브라우저에 취향을 저장합니다. 가격 알림은 가입 후 상품별로 목표가를 정해야 시작됩니다.")}</p></fieldset>
          <Notice error={error} /><div className="flex gap-3"><button type="button" className="btn-outline" disabled={busy || created} onClick={() => setStep(1)}>{t("이전")}</button>
            <button className="btn-primary flex-1" disabled={busy || !valid}>{busy ? t("처리 중…") : created ? t("로그인하고 완료") : t("가입 완료하기")}<Icon name="arrow-right" /></button></div>
        </form>}
        {step === 3 && <>
          <p className="mt-3 text-sm leading-7 text-slate-500">{t("계정 생성이 완료되었습니다.")}{" "}{alertSaved ? t("등록한 목표가는 관심 상품에서 언제든 바꿀 수 있어요.") : t("아래 상품의 알림 버튼을 눌러 첫 목표가를 등록해 보세요.")}</p>
          {!!categories.length && <div className="my-5 flex flex-wrap gap-2">{categories.map((c) => <span key={c} className="badge bg-brand-50 text-brand-700">{c}</span>)}</div>}
          <div className="my-6">{recommendations.loading ? <Loading /> : recommendations.error ? <Notice error={recommendations.error} /> : !picks.length ? <Empty title={t("선택한 카테고리의 상품을 준비하고 있어요")}>{t("상품 탐색에서 다른 품목을 골라보세요.")}</Empty>
            : <div className="grid gap-4 sm:grid-cols-3">{picks.map((p) => <div key={p.id} className="overflow-hidden rounded-xl border border-slate-200"><Photo product={p} /><div className="p-4"><h3 className="min-h-12 text-sm">{p.name}</h3><p className="numeric my-3 text-lg">{won(priceOf(p))}</p><button className="btn-outline w-full" onClick={() => openWatch(p, null, () => setAlertSaved(true))}><Icon name="bell" />{t("목표가 알림")}</button></div></div>)}</div>}</div>
          <div className="flex flex-wrap gap-3"><Link to="/watchlist" className="btn-primary">{t("내 관심 상품 보기")}<Icon name="arrow-right" /></Link><Link className="btn-ghost" to="/search">{t("다른 상품 둘러보기")}</Link></div>
        </>}
      </section>
    </div>
  </div>;
}
function Chat() {
  const { id } = useParams(); const product = useApi(`/products/${id}`); const timing = useApi(`/products/${id}/timing`);
  const [messages, setMessages] = useState([]); const [question, setQuestion] = useState(''); const [busy, setBusy] = useState(false); const [remaining, setRemaining] = useState(null);
  const box = useRef(null);
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }); }, [messages, busy]);
  async function ask(q) {
    if (!q.trim() || busy) return; setBusy(true); setQuestion('');
    setMessages((m) => [...m, { role: 'user', text: q.trim() }]);
    try { const r = await api.post('/ai/chat', { product_id: Number(id), question: q.trim() }); setRemaining(r.remaining); setMessages((m) => [...m, { role: 'ai', text: r.answer }]); }
    catch (err) { setMessages((m) => [...m, { role: 'error', text: err.message }]); } finally { setBusy(false); }
  }
  if (product.loading || timing.loading) return <Loading />;
  if (product.error || timing.error) return <div className="container-x py-8"><Notice error={product.error || timing.error} /></div>;
  return <div className="container-x grid grid-cols-1 gap-6 py-10 lg:grid-cols-[300px_minmax(0,1fr)]">
    <aside className="card h-fit overflow-hidden"><Photo product={product.data} /><div className="p-5"><p className="text-xs text-slate-500">{product.data.category}</p><h1 className="mt-2 text-xl">{product.data.name}</h1><p className="numeric my-4 text-2xl">{won(timing.data.current_price)}</p><TimingGauge timing={timing.data} compact /><Link className="btn-outline mt-6 w-full" to={`/product/${id}`}>{t("상품 상세로 돌아가기")}</Link></div></aside>
    <section className="card flex min-h-[550px] flex-col"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-5"><h2 className="text-xl"><Icon name="wand-magic-sparkles" className="mr-2 text-brand-600" />{t("구매 타이밍 상담")}</h2><span className="text-xs text-slate-500">{remaining == null ? t("가격 데이터 기반 답변") : t("오늘 {n}회 남음", { n: remaining })}</span></div>
      <div className="max-h-[55vh] min-h-72 flex-1 space-y-4 overflow-y-auto p-5" role="log" aria-label={t("AI 상담 내역")} aria-live="polite" ref={box}>
        <p className="max-w-md rounded-2xl bg-slate-50 p-4 text-sm leading-7">{product.data.name}{t("의 가격과 구매 시점을 함께 살펴볼까요? 궁금한 점을 물어보세요.")}</p>
        {messages.map((m, i) => <div key={i} className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl p-4 text-sm leading-7 ${m.role === 'user' ? 'ml-auto bg-brand-600 text-white' : m.role === 'error' ? 'bg-rose-50 text-rose-800' : 'bg-slate-50'}`}><span className="sr-only">{m.role === 'user' ? t("나: ") : 'AI: '}</span>{m.text}</div>)}
        {busy && <p role="status" className="text-sm text-slate-500"><Icon name="circle-notch" className="mr-2 animate-spin" />{t("가격 데이터를 살펴보고 있어요…")}</p>}
      </div>
      <div className="border-t border-slate-200 p-4"><div className="mb-4 flex flex-wrap gap-2">{[t("다음 주까지 기다리면 더 싸질까?"), t("역대 최저가는 언제였어?"), t("어느 쇼핑몰이 제일 싸?")].map((q) => <button key={q} className="filter-chip whitespace-normal text-xs" disabled={busy} onClick={() => ask(q)}>{q}</button>)}</div>
        <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); ask(question); }}><input className="input" aria-label={t("구매 타이밍 질문")} placeholder={t("가격이나 구매 시점을 물어보세요")} maxLength={200} value={question} onChange={(e) => setQuestion(e.target.value)} /><button className="btn-primary" disabled={busy || !question.trim()} aria-label={t("질문 보내기")}><Icon name="paper-plane" /></button></form>
        <p className="mt-3 text-[11px] text-slate-500">{t("분석은 참고 정보이며 실제 가격 변화와 다를 수 있습니다.")}</p></div>
    </section>
  </div>;
}
function OAuthCallback() {
  const { setUser } = useAuth(); const nav = useNavigate(); const [error, setError] = useState(null);
  const callback = useRef(new URLSearchParams(window.location.hash.slice(1)));
  useEffect(() => {
    let active = true;
    const token = callback.current.get('token'); const next = safeNext(callback.current.get('next'));
    // 토큰이 브라우저 주소와 뒤로가기 기록에 남지 않게 제거한다.
    window.history.replaceState(null, '', window.location.pathname);
    if (!token) { setError(new Error(t("로그인 정보를 받지 못했습니다. 다시 로그인해 주세요."))); return; }
    localStorage.setItem('pt_token', token);
    api.get('/users/me').then((u) => { if (!active) return; auth.save(token, u); setUser(u); nav(next, { replace: true }); })
      .catch((err) => { if (active) { auth.clear(); setUser(null); setError(err); } });
    return () => { active = false; };
  }, [nav, setUser]);
  return <div className="container-x max-w-lg py-16">{error ? <><Notice error={error} /><Link className="btn-primary" to="/login">{t("로그인으로 돌아가기")}</Link></> : <Loading text={t("소셜 로그인을 마무리하고 있어요")} />}</div>;
}
function InfoPage({ kind }) {
  const info = {
    guide: [t("구매 타이밍을 읽는 방법"), [
      [t("가격 비교의 기준"), t("배송비를 합한 실구매가를 비교합니다. 수집 시각 이후 쿠폰, 회원 등급, 재고에 따라 실제 결제 금액은 달라질 수 있습니다. 판매처에서 마지막으로 확인해 주세요.")],
      [t("역대 최저가와 90일 최저가"), t("역대 최저가는 서비스에 기록된 전체 기간 중 가장 낮은 가격입니다. 수집 이전 가격은 포함하지 않습니다. 90일 최저가는 최근 3개월의 관측값을 기준으로 합니다.")],
      [t("지금 사세요 / 기다리세요"), t("구매 적기 점수는 과거 가격의 위치와 하락 가능성 등을 종합한 0~100점의 참고 지표입니다. 70점 이상은 지금 구매, 40점 이상은 조금 대기, 그 미만은 대기를 권장합니다. 가격 이력이 30일 미만이면 판단을 보류합니다.")],
      [t("목표가 알림"), t("상품의 알림 버튼에서 원하는 가격을 정하세요. 수집된 실구매가가 목표가 이하가 되면 사이트의 가격 알림에 표시합니다. 이메일이나 문자, 브라우저 푸시는 보내지 않습니다.")],
    ]],
    terms: [t("서비스 이용 안내"), [
      [t("서비스 범위"), t("TimePick은 가격 비교와 구매 타이밍 분석을 제공하는 팀 프로젝트입니다. 상품 판매, 결제, 배송은 각 판매처에서 처리합니다.")],
      [t("가격·분석 정보"), t("가격은 하루 4회(0·6·12·18시) 수집하며 수집 환경에 따라 지연되거나 누락될 수 있습니다. 적기 예측과 AI 답변은 참고 정보입니다. 구매 결과나 미래 가격을 보장하지 않습니다.")],
      [t("이미지와 데모"), t("상품 사진은 제조사 공식 이미지이며, 찾지 못한 상품은 다나와·에누리 상품 이미지를 쓰고 사진 아래에 출처를 표시합니다. 사진이 없으면 카테고리 아이콘이 나옵니다. 화면 상단에 체험 공간으로 표시되는 경우 가격과 계정은 데모 데이터이고, 상품 사진은 카테고리를 설명하는 Unsplash 참고 이미지입니다.")],
      [t("문의"), t("프로젝트 GitHub Issues에서 오류를 제보할 수 있습니다. 비밀번호, 토큰, 이메일 등의 개인정보를 공개 이슈에 올리지 마세요.")],
    ]],
    privacy: [t("개인정보 처리 안내"), [
      [t("계정과 이용 정보"), t("운영 서비스는 이름, 이메일, 비밀번호 해시 및 계정 권한을 저장합니다. 관심 상품, 목표가, 가격 알림은 계정에 연결해 관리합니다.")],
      [t("브라우저 저장소"), t("로그인 상태는 이 브라우저의 로컬 저장소에 보관됩니다. 관심 카테고리도 계정별로 이 브라우저에 저장되며 다른 기기에 동기화되지 않습니다. 공용 기기에서는 이용 후 로그아웃해 주세요.")],
      [t("소셜 로그인"), t("선택한 제공자의 동의 화면을 거쳐 전달받은 이메일과 프로필 이름을 계정 연결에 사용합니다. 제공자의 비밀번호를 TimePick에 입력하지 않습니다.")],
      [t("외부 서비스"), t("가격 데이터 기반 AI 조언에는 서버에서 Gemini를 사용할 수 있습니다. 상담창에 개인정보를 입력하지 마세요. 글꼴과 이미지를 불러올 때 Google Fonts, Spoqa, Unsplash(로그인 화면·데모 상품), 제조사·다나와·에누리 이미지 서버에 브라우저 요청이 전송됩니다.")],
      [t("문의와 데이터 요청"), t("현재 셀프서비스 계정 삭제 기능은 제공하지 않습니다. 계정과 데이터 관련 요청은 프로젝트 운영자에게 문의해 주세요. 공개 GitHub Issues에는 개인정보를 기재하지 마세요.")],
    ]],
  }[kind];
  return <div className="container-x max-w-3xl py-12"><h1 className="section-title">{info[0]}</h1><div className="mt-8 space-y-8">{info[1].map(([title, copy]) => <section key={title}><h2 className="text-lg">{title}</h2><p className="mt-3 text-sm leading-8 text-slate-600">{copy}</p></section>)}</div><Link to="/search" className="btn-primary mt-10">{t("가격 탐색하기")}</Link></div>;
}
function Protected({ children, admin = false }) {
  const { user, ready } = useAuth(); const location = useLocation();
  if (!ready) return <Loading text={t("로그인 상태 확인 중")} />;
  if (!user) return <Navigate replace to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} />;
  if (admin && user.role !== 'ADMIN') return <div className="container-x py-12"><Empty title={t("관리자 전용 화면입니다")} icon="lock"><Link to="/" className="btn-primary mt-4">{t("홈으로 돌아가기")}</Link></Empty></div>;
  return children;
}
function AdminLayout() {
  return <div className="container-x py-8"><nav className="mb-8 flex flex-wrap gap-2" aria-label={t("관리자 메뉴")}>{[['/admin', t("수집 현황")], ['/admin/ai', t("AI 사용량")], ['/admin/users', t("회원 관리")]].map(([to, label]) => <NavLink end key={to} to={to} className={({ isActive }) => isActive ? 'btn-primary' : 'btn-outline'}>{label}</NavLink>)}</nav><Suspense fallback={<Loading />}><Outlet /></Suspense></div>;
}
function RouteFocus() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    document.title = t("타임픽 · 가격을 비교하고, 살 때를 발견하세요");
    if (hash && !pathname.startsWith('/oauth/')) document.getElementById(hash.slice(1))?.scrollIntoView();
    else { window.scrollTo({ top: 0, behavior: 'instant' }); document.getElementById('main-content')?.focus({ preventScroll: true }); }
  }, [pathname, hash]);
  return null;
}
class PageBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div className="container-x py-16"><Empty title={t("화면을 불러오지 못했습니다")} icon="triangle-exclamation"><p>{t("새로고침 후 다시 시도해 주세요.")}</p><button className="btn-primary mt-4" onClick={() => window.location.reload()}>{t("새로고침")}</button></Empty></div>;
    return this.props.children;
  }
}
function Application() {
  const { user } = useAuth(); const nav = useNavigate(); const location = useLocation();
  const [selection, setSelection] = useState(null); const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((v) => v + 1), []);
  function openWatch(product, watch = null, afterSave = null) {
    if (!user) { nav(`/login?next=${encodeURIComponent(`/product/${product.id}`)}`); return; }
    setSelection({ product, watch, afterSave });
  }
  useEffect(() => setSelection(null), [location.pathname, user?.id]);
  return <UIContext.Provider value={{ openWatch, revision, refresh }}>
    <a href="#main-content" className="skip-link">{t("본문 바로가기")}</a><Header /><RouteFocus />
    <main id="main-content" tabIndex={-1} className="min-h-[55vh] outline-none">
      <PageBoundary key={location.pathname}><Routes>
        <Route path="/" element={<Home />} /><Route path="/search" element={<Protected><Explore /></Protected>} />
        <Route path="/product/:id" element={<Protected><ProductDetail key={location.pathname} /></Protected>} />
        <Route path="/watchlist" element={<Protected><Watchlist /></Protected>} /><Route path="/alerts" element={<Protected><Alerts /></Protected>} />
        <Route path="/chat/:id" element={<Protected><Chat key={location.pathname} /></Protected>} />
        <Route path="/login" element={<Login />} /><Route path="/signup" element={<Signup />} /><Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route path="/admin" element={<Protected admin><AdminLayout /></Protected>}>
          <Route index element={<Admin />} /><Route path="ai" element={<AdminAI />} /><Route path="users" element={<AdminUsers />} />
        </Route>
        {['terms', 'privacy', 'guide'].map((kind) => <Route path={`/${kind}`} key={kind} element={<InfoPage kind={kind} />} />)}
        <Route path="*" element={<div className="container-x py-16"><Empty title={t("이 페이지는 찾을 수 없어요")} icon="compass"><Link className="btn-primary mt-5" to="/">{t("홈으로 돌아가기")}</Link></Empty></div>} />
      </Routes></PageBoundary>
    </main><Footer />
    {selection && <WatchDialog key={`${user?.id}-${selection.product.id}`} selection={selection} onClose={() => setSelection(null)} onSaved={() => { refresh(); selection.afterSave?.(); }} />}
  </UIContext.Provider>;
}
/** 화면 설정: 라이트/다크 테마(즉시 전환·저장), 한국어/영어(저장 후 다시 불러오기) */
function Preferences({ wide = false }) {
  const [theme, setTheme] = useState(currentTheme);
  const toggleTheme = () => { const next = theme === 'dark' ? 'light' : 'dark'; applyTheme(next); setTheme(next); };
  const other = LANG === 'ko' ? 'en' : 'ko';
  return <div className={`flex items-center gap-1 ${wide ? 'justify-between' : ''}`}>
    <button type="button" className="icon-btn" onClick={toggleTheme} aria-pressed={theme === 'dark'}
      aria-label={theme === 'dark' ? t('라이트 모드로 전환') : t('다크 모드로 전환')} title={theme === 'dark' ? t('라이트 모드로 전환') : t('다크 모드로 전환')}>
      <Icon name={theme === 'dark' ? 'sun' : 'moon'} /></button>
    <button type="button" className="btn-ghost min-w-11 px-3 text-xs font-medium" onClick={() => setLang(other)} lang={other}
      aria-label={t('English로 보기')} title={t('English로 보기')}><Icon name="globe" />{other === 'en' ? 'EN' : '한국어'}</button>
  </div>;
}

export default function App() {
  return <ToastProvider><AuthProvider><Application /></AuthProvider></ToastProvider>;
}
