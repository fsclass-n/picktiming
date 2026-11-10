import { useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api.js';
import { dt, pct } from '../lib/format.js';
import { ErrorBox, Plot, Spinner, StatCard } from '../components/ui.jsx';
import { t } from '../lib/i18n.js';

export default function AdminAI() {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.get('/admin/ai-metrics').then(setD).catch(setError); }, []);
  const x = useMemo(() => d?.daily.map((r) => r.date) || [], [d]);
  const calls = useMemo(() => d && [
    { x, y: d.daily.map((r) => r.calls), type: 'bar', name: t("호출"), marker: { color: '#7c4dff' } },
    { x, y: d.daily.map((r) => r.cache_hits), type: 'scatter', mode: 'lines+markers', name: t("캐시 적중"), line: { color: '#10b981' } }], [d, x]);
  const latency = useMemo(() => d && [{ x, y: d.daily.map((r) => r.avg_latency_ms), type: 'scatter', mode: 'lines+markers', name: t("평균 응답(ms)"), line: { color: '#f97316' } }], [d, x]);
  const layout = useMemo(() => ({ xaxis: { type: 'category' } }), []);
  const latLayout = useMemo(() => ({ xaxis: { type: 'category' }, shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 3000, y1: 3000, line: { dash: 'dot', color: '#e11d48' } }] }), []);

  if (error) return <ErrorBox error={error} />;
  if (!d) return <Spinner />;
  const s = d.summary;
  return (
    <>
      <h1 className="text-3xl">{t("관리자 · AI 사용량")}</h1>
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard label={t("7일 호출 수")} value={s.calls_7d.toLocaleString('ko-KR')} icon="fa-wand-magic-sparkles" />
        <StatCard label={t("평균 응답")} value={t("{n}초", { n: (s.avg_latency_ms / 1000).toFixed(1) })} icon="fa-stopwatch" />
        <StatCard label={t("7일 토큰")} value={s.tokens_7d.toLocaleString('ko-KR')} icon="fa-coins" />
        <StatCard label={t("캐시 적중률")} value={pct(s.cache_hit_rate)} icon="fa-bolt" />
        <StatCard label={t("검증 실패율")} value={pct(s.validation_fail_rate, 2)} icon="fa-shield-halved" />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="card p-5"><h2 className="text-lg">{t("일별 호출")}</h2><Plot data={calls} layout={layout} height={300} /></section>
        <section className="card p-5"><h2 className="text-lg">{t("평균 응답 시간 (목표 3초)")}</h2><Plot data={latency} layout={latLayout} height={300} /></section>
      </div>
      <section className="card mt-6 overflow-x-auto p-5"><h2 className="mb-3 text-lg">{t("최근 호출")}</h2>
        <table className="table-x"><thead><tr><th>{t("시각")}</th><th>{t("유형")}</th><th>{t("상품")}</th><th className="text-right">{t("응답(ms)")}</th><th>{t("캐시")}</th><th>{t("검증")}</th></tr></thead>
          <tbody>{d.recent.map((r, i) => (
            <tr key={i}><td className="whitespace-nowrap">{dt(r.created_at)}</td><td>{r.type}</td><td>{r.product}</td><td className="text-right">{r.latency_ms.toLocaleString('ko-KR')}</td>
              <td>{r.cache_hit ? <span className="badge bg-emerald-100 text-emerald-700">{t("적중")}</span> : '-'}</td>
              <td><span className={`badge ${r.validation === 'OK' ? 'bg-slate-100' : 'bg-amber-100 text-amber-700'}`}>{r.validation}</span></td></tr>))}</tbody></table>
        <p className="mt-3 text-xs text-slate-500">{t("모델:")}{" "}{s.model}</p></section>
    </>
  );
}
