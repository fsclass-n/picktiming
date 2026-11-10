import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { dt } from '../lib/format.js';
import { ErrorBox, Icon, Spinner, StatCard } from '../components/ui.jsx';
import { useToast } from '../components/Toast.jsx';
import { t } from '../lib/i18n.js';

/** 관리자: 회원 목록 조회와 권한 변경(일반 사용자 ↔ 관리자) */
export default function AdminUsers() {
  const { user: me } = useAuth();
  const toast = useToast();
  const [q, setQ] = useState('');
  const [role, setRole] = useState('');
  const [page, setPage] = useState(1);
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setError(null);
    api.get(`/admin/users?q=${encodeURIComponent(q.trim())}&role=${role}&page=${page}&size=20`).then(setD).catch(setError);
  }, [q, role, page]);
  useEffect(() => { load(); }, [role, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const change = async (u) => {
    const next = u.role === 'ADMIN' ? 'USER' : 'ADMIN';
    if (!window.confirm(t("{name}({email}) 님을 {role}(으)로 변경할까요?", { name: u.name, email: u.email, role: next === 'ADMIN' ? t("관리자") : t("일반 사용자") }))) return;
    try { await api.patch(`/admin/users/${u.id}/role`, { role: next }); toast(t("권한을 변경했습니다."), 'success'); load(); } catch (err) { toast(err.message, 'danger'); }
  };
  const pages = d ? Math.max(1, Math.ceil(d.total / d.size)) : 1;

  return (
    <>
      <h1 className="text-3xl">{t("관리자 · 회원 관리")}</h1>
      {d && <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t("전체 회원")} value={d.summary.users.toLocaleString('ko-KR')} icon="fa-users" />
        <StatCard label={t("관리자")} value={d.summary.admins} icon="fa-user-shield" /></div>}
      <form className="mt-6 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); setPage(1); load(); }}>
        <input className="input max-w-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("이름·이메일 검색")} aria-label={t("회원 검색")} />
        <select className="input w-40" value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }} aria-label={t("권한 필터")}>
          <option value="">{t("전체 권한")}</option><option value="USER">{t("일반 사용자")}</option><option value="ADMIN">{t("관리자")}</option></select>
        <button className="btn-primary"><Icon name="fa-magnifying-glass" />{t("검색")}</button>
      </form>
      <div className="mt-4"><ErrorBox error={error} /></div>
      <section className="card mt-4 overflow-x-auto">
        {!d ? <Spinner /> : !d.items.length ? <p className="p-6 text-sm text-slate-500">{t("조건에 맞는 회원이 없습니다.")}</p> : (
          <table className="table-x">
            <thead><tr><th>{t("회원")}</th><th>{t("권한")}</th><th className="text-right">{t("관심 상품")}</th><th>{t("가입일")}</th><th className="text-right">{t("권한 변경")}</th></tr></thead>
            <tbody>{d.items.map((u) => (
              <tr key={u.id}>
                <td><div className="font-semibold">{u.name}</div><div className="text-xs text-slate-500">{u.email}</div></td>
                <td><span className={`badge ${u.role === 'ADMIN' ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-600'}`}>
                  <Icon name={u.role === 'ADMIN' ? 'fa-user-shield' : 'fa-user'} />{u.role === 'ADMIN' ? t("관리자") : t("일반 사용자")}</span></td>
                <td className="text-right">{u.watch_count}</td><td className="whitespace-nowrap">{dt(u.created_at)}</td>
                <td className="text-right">{u.id === me?.id ? <span className="text-xs text-slate-400">{t("본인")}</span> : (
                  <button className="btn-outline px-3 py-1.5" onClick={() => change(u)}>
                    <Icon name={u.role === 'ADMIN' ? 'fa-arrow-down' : 'fa-arrow-up'} />{u.role === 'ADMIN' ? t("일반으로") : t("관리자로")}</button>)}</td>
              </tr>))}</tbody>
          </table>)}
      </section>
      {d && pages > 1 && <div className="mt-4 flex justify-center gap-2">
        <button className="btn-outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("이전")}</button>
        <span className="self-center text-sm">{page} / {pages}</span>
        <button className="btn-outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t("다음")}</button></div>}
      <p className="mt-4 text-xs text-slate-500"><Icon name="fa-circle-info" className="mr-1" />{t("테스트 관리자 계정은 조회만 가능합니다. 자기 자신과 마지막 관리자의 권한은 바꿀 수 없습니다.")}</p>
    </>
  );
}
