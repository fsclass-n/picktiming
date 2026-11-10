// 라이트/다크 테마. 처음에는 기기 설정(prefers-color-scheme)을 따르고, 사용자가 바꾸면 저장한다.
// index.html의 인라인 스크립트가 첫 화면을 그리기 전에 같은 규칙으로 data-theme를 붙여 깜박임을 막는다.
const KEY = 'tp_theme';

export function currentTheme() {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

export function applyTheme(theme, save = true) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  if (save) {
    try { localStorage.setItem(KEY, theme); } catch { /* 저장 실패 시 이번 방문에만 적용 */ }
  }
}
