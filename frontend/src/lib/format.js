export { PASSWORD_RULE } from './mock.js';
import { LOCALE, money, t } from './i18n.js';

export const LABELS = {
  BUY_NOW: { text: t("지금 구매"), cls: 'bg-emerald-100 text-emerald-700', bar: 'bg-emerald-500', icon: 'fa-bag-shopping' },
  WAIT_A_BIT: { text: t("조금 대기"), cls: 'bg-amber-100 text-amber-700', bar: 'bg-amber-500', icon: 'fa-hourglass-half' },
  WAIT: { text: t("대기 권장"), cls: 'bg-rose-100 text-rose-700', bar: 'bg-rose-500', icon: 'fa-circle-pause' },
  HOLD: { text: t("판단 보류"), cls: 'bg-slate-100 text-slate-600', bar: 'bg-slate-400', icon: 'fa-circle-question' },
};
const CATEGORY_ICONS = { 디지털: 'fa-headphones', 가전: 'fa-plug', 생필품: 'fa-basket-shopping', 유아: 'fa-baby' };

export const won = (n) => (n == null ? '-' : money(n));
export const pct = (v, digits = 0) => (v == null ? '-' : `${(v * 100).toFixed(digits)}%`);
export const dt = (iso) => (iso ? new Date(iso).toLocaleString(LOCALE, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-');
export const categoryIcon = (c) => CATEGORY_ICONS[c] || 'fa-box';
export const label = (l) => LABELS[l] || LABELS.HOLD;
