import { useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api.js';
import { dt, pct } from '../lib/format.js';
import { ErrorBox, Icon, Plot, Spinner, StatCard } from '../components/ui.jsx';
import { t } from '../lib/i18n.js';

const STATUS = { SUCCESS: 'bg-emerald-100 text-emerald-700', PARTIAL: 'bg-amber-100 text-amber-700', FAIL: 'bg-rose-100 text-rose-700', RUNNING: 'bg-sky-100 text-sky-700' };

/** 지금 수집: 실제 관리자만 GitHub Actions 수집을 실행한다(서버가 권한·10분 간격을 다시 확인) */
function CollectPanel() {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => { api.get('/admin/collect').then(setState).catch(() => setState({ allowed: false, configured: false, reason: '' })); }, []);
  if (!state) return null;
  const run = async () => {
    setBusy(true); setMessage('');
    try { setMessage(t((await api.post('/admin/collect')).message)); } catch (e) { setMessage(e.message); } finally { setBusy(false); }
  };
  const disabled = busy || !state.allowed || !state.configured;
  return <section className="card mt-6 flex flex-wrap items-center justify-between gap-4 p-5" aria-labelledby="collect-title">
    <div><h2 id="collect-title" className="text-lg">{t('수동 수집')}</h2>
      <p className="mt-1 text-sm text-slate-500">{!state.allowed ? t(state.reason) : !state.configured ? t('수동 수집이 설정되지 않았습니다. Render에 GITHUB_DISPATCH_TOKEN을 등록해 주세요.') : t('다나와·에누리 가격을 지금 수집합니다(10분에 한 번).')}
        {state.last_requested_at && <> {t('마지막 요청')} {dt(state.last_requested_at)}</>}</p>
      {message && <p className="mt-2 text-sm text-brand-700" role="status">{message}</p>}</div>
    <button type="button" className="btn-primary" onClick={run} disabled={disabled} aria-disabled={disabled}>
      <Icon name={busy ? 'circle-notch' : 'rotate'} className={busy ? 'animate-spin' : ''} />{busy ? t('요청 중…') : t('지금 수집')}</button>
  </section>;
}

export default function Admin() {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.get('/admin/rpa-logs').then(setD).catch(setError); }, []);
  const chart = useMemo(() => d && [
    { x: d.daily.map((r) => r.date), y: d.daily.map((r) => r.collected), type: 'bar', name: t("수집 성공"), marker: { color: '#7c4dff' } },
    { x: d.daily.map((r) => r.date), y: d.daily.map((r) => r.failed), type: 'scatter', mode: 'lines+markers', name: t("실패 건수"), line: { color: '#e11d48' }, yaxis: 'y2' },
  ], [d]);
  const layout = useMemo(() => ({ xaxis: { type: 'category' }, yaxis: { rangemode: 'tozero' }, yaxis2: { overlaying: 'y', side: 'right', showgrid: false, rangemode: 'tozero' } }), []);

  if (error) return <ErrorBox error={error} />;
  if (!d) return <Spinner />;
  const active = d.models.find((m) => m.active);
  return (
    <>
      <h1 className="text-3xl">{t("관리자 · 수집·모델")}</h1>
      <CollectPanel />
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t("오늘 수집 실행")} value={t("{n}회", { n: d.summary.runs_today })} icon="fa-play" />
        <StatCard label={t("7일 수집 성공률")} value={pct(d.summary.success_rate, 1)} icon="fa-circle-check" />
        <StatCard label={t("오늘 수집 건수")} value={d.summary.collected_today.toLocaleString('ko-KR')} icon="fa-database" />
        <StatCard label={t("운영 모델 F1")} value={active ? active.f1.toFixed(2) : '-'} icon="fa-brain" />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className="card p-5 lg:col-span-2"><h2 className="text-lg">{t("최근 7일 수집")}</h2><Plot data={chart} layout={layout} /></section>
        <section className="card overflow-x-auto p-5"><h2 className="mb-3 text-lg">{t("모델 버전")}</h2>
          <table className="table-x"><thead><tr><th>{t("버전")}</th><th className="text-right">F1</th><th className="text-right">{t("학습 행")}</th></tr></thead>
            <tbody>{d.models.map((m) => (
              <tr key={m.version}><td>{m.version} {m.active && <span className="badge bg-emerald-100 text-emerald-700">{t("운영")}</span>}<div className="text-xs text-slate-500">{m.algorithm}</div></td>
                <td className="text-right">{m.f1?.toFixed(2) ?? '-'}</td><td className="text-right">{(m.trained_rows || 0).toLocaleString('ko-KR')}</td></tr>))}</tbody></table></section>
      </div>
      <section className="card mt-6 overflow-x-auto p-5"><h2 className="mb-3 text-lg">{t("작업 로그")}</h2>
        <table className="table-x"><thead><tr><th>{t("시작")}</th><th>{t("작업")}</th><th>{t("상태")}</th><th className="text-right">{t("처리")}</th><th className="text-right">{t("실패")}</th><th>{t("메시지")}</th></tr></thead>
          <tbody>{d.logs.map((l) => (
            <tr key={l.id}><td className="whitespace-nowrap">{dt(l.started_at)}</td><td><code className="text-xs">{l.job_name}</code></td>
              <td><span className={`badge ${STATUS[l.status] || 'bg-slate-100'}`}>{l.status}</span></td>
              <td className="text-right">{(l.collected || 0).toLocaleString('ko-KR')}</td><td className="text-right">{l.failed}</td><td className="text-xs">{l.message}</td></tr>))}</tbody></table></section>
    </>
  );
}
