// 한국어/영어 화면 문구. 원문(한국어)을 키로 쓰고, 영어 사전에 없으면 원문을 그대로 보여 준다.
//   t('로그인') → 'Log in' (영어) / '로그인' (한국어)
//   t('최저 {min}', { min: won(1000) }) → 'Low ₩1,000'
// 언어를 바꾸면 저장 후 화면을 다시 불러온다. 모듈 수준 상수(메뉴·안내 문구)까지 같은 언어로 맞추기 위해서다.
// 상품명·판매처·AI 답변처럼 서버가 보내는 데이터는 번역하지 않는다.
import EN from './i18n-en.js';

const KEY = 'tp_lang';
export const LANGS = { ko: '한국어', en: 'English' };

function initialLang() {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved in LANGS) return saved;
  } catch { /* 저장소를 쓸 수 없으면 기본값 */ }
  return 'ko';
}

export const LANG = initialLang();
export const LOCALE = LANG === 'en' ? 'en-US' : 'ko-KR';
if (typeof document !== 'undefined') document.documentElement.lang = LANG;

export function t(text, vars) {
  let out = LANG === 'en' ? (EN[text] ?? text) : text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
  return out;
}

export function setLang(next) {
  if (!(next in LANGS) || next === LANG) return;
  try { localStorage.setItem(KEY, next); } catch { /* 저장 실패 시에도 이번 화면은 바꾼다 */ }
  window.location.reload();
}

/** 금액: 315,000원 / ₩315,000 */
export const money = (n) => t('{n}원', { n: Number(n).toLocaleString(LOCALE) });
