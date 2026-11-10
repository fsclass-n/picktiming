import { useEffect, useRef, useState } from 'react';
import { t } from '../lib/i18n.js';

export const Icon = ({ name, className = '' }) => <i className={`fa-solid ${name} ${className}`} aria-hidden="true" />;

export function Spinner({ text = t("불러오는 중…") }) {
  return <div className="py-12 text-center text-sm text-slate-500"><Icon name="fa-spinner" className="mr-2 animate-spin" />{text}</div>;
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"><Icon name="fa-triangle-exclamation" className="mr-2" />{error.message || String(error)}</div>;
}

export function StatCard({ label: text, value, icon }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 text-xs text-slate-500"><Icon name={icon} className="text-brand-500" />{text}</div>
      <div className="numeric mt-1 text-2xl text-slate-900">{value}</div>
    </div>
  );
}

let plotlyPromise;
function loadPlotly() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  if (!plotlyPromise) plotlyPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.plot.ly/plotly-2.35.2.min.js';
    script.async = true;
    const timeout = setTimeout(() => fail(), 20000);
    const fail = () => { clearTimeout(timeout); script.remove(); plotlyPromise = null; reject(new Error(t("차트를 불러오지 못했습니다. 네트워크 연결을 확인하고 새로고침해 주세요."))); };
    script.onload = () => { clearTimeout(timeout); if (window.Plotly) resolve(window.Plotly); else fail(); };
    script.onerror = fail;
    document.head.appendChild(script);
  });
  return plotlyPromise;
}

/** 관리자 통계에서만 Plotly를 요청한다. CDN 오류 시 무한 대기 대신 오류를 표시한다. */
export function Plot({ data, layout, height = 320 }) {
  const ref = useRef(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true; const node = ref.current;
    setError(null); setLoading(true);
    loadPlotly().then(async (plotly) => {
      if (!alive) return;
      await plotly.react(node, data, { height, margin: { l: 60, r: 20, t: 10, b: 40 }, font: { family: 'Noto Sans KR, Malgun Gothic', color: document.documentElement.dataset.theme === 'dark' ? '#cbd5e1' : '#334155' },
        legend: { orientation: 'h', y: -0.2 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', ...layout }, { displayModeBar: false, responsive: true });
      if (alive) setLoading(false);
    }).catch((err) => { if (alive) { setError(err); setLoading(false); } });
    const resize = new ResizeObserver(() => { if (alive && node?.data) window.Plotly?.Plots.resize(node); });
    resize.observe(node);
    return () => {
      alive = false; resize.disconnect();
      if (node?.data && window.Plotly) window.Plotly.purge(node);
    };
  }, [data, layout, height]);
  return <div>{loading && <Spinner text={t("통계 차트 불러오는 중…")} />}<ErrorBox error={error} /><div ref={ref} style={{ minHeight: error || loading ? 0 : height }} /></div>;
}
