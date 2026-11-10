// 한국어 문구를 t('…')로 감싸는 1회성 변환 도구. node scripts/i18n-wrap.mjs [--write] <파일...>
// JSX 텍스트·JSX 속성·문자열 리터럴만 바꾸고, 객체 키·비교식·import·이미 t()인 곳은 건너뛴다.
// --report: 바꿀 리터럴 위치를 출력(데이터 값이 화면 문구로 잘못 바뀌지 않는지 검토용)
import { readFileSync, writeFileSync } from 'node:fs';
import { parseAst } from 'rolldown/parseAst';

const HANGUL = /[가-힣]/;
const args = process.argv.slice(2);
const write = args.includes('--write');
const report = args.includes('--report');
const skipLines = new Set((args.find((a) => a.startsWith('--skip=')) || '--skip=').slice(7).split(',').filter(Boolean));
const files = args.filter((a) => !a.startsWith('--'));
const keys = new Set();

function walk(node, parent, visit) {
  if (!node || typeof node.type !== 'string') return;
  visit(node, parent);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach((child) => child && typeof child.type === 'string' && walk(child, node, visit));
    else if (value && typeof value.type === 'string') walk(value, node, visit);
  }
}

for (const file of files) {
  const src = readFileSync(file, 'utf8');
  const ast = parseAst(src, { lang: 'jsx', sourceType: 'module' });
  const lineOf = (pos) => src.slice(0, pos).split('\n').length;
  const edits = [];
  const templates = [];
  walk(ast, null, (node, parent) => {
    if (node.type === 'JSXText' && HANGUL.test(node.value)) {
      const key = node.value.replace(/\s+/g, ' ').trim();
      const lead = node.value.match(/^\s*/)[0].length;
      const trail = node.value.match(/\s*$/)[0].length;
      const lead1 = node.value.slice(0, lead).includes('\n') ? '' : node.value.slice(0, lead);
      const trail1 = node.value.slice(node.value.length - trail).includes('\n') ? '' : node.value.slice(node.value.length - trail);
      edits.push([node.start, node.end, `${lead1 ? `{${JSON.stringify(lead1)}}` : ''}{t(${JSON.stringify(key)})}${trail1 ? `{${JSON.stringify(trail1)}}` : ''}`, key]);
    } else if (node.type === 'Literal' && typeof node.value === 'string' && HANGUL.test(node.value)) {
      if (parent?.type === 'Property' && parent.key === node && !parent.computed) return;
      if (parent?.type === 'ImportDeclaration' || parent?.type === 'SwitchCase') return;
      if (parent?.type === 'BinaryExpression' && ['===', '!==', '==', '!='].includes(parent.operator)) return;
      if (parent?.type === 'CallExpression' && parent.callee?.name === 't') return;
      if (skipLines.has(`${file}:${lineOf(node.start)}`)) return;
      const inJsxAttr = parent?.type === 'JSXAttribute';
      edits.push([node.start, node.end, inJsxAttr ? `{t(${JSON.stringify(node.value)})}` : `t(${JSON.stringify(node.value)})`, node.value, lineOf(node.start)]);
    } else if (node.type === 'TemplateLiteral' && node.quasis.some((q) => HANGUL.test(q.value.cooked))) {
      templates.push(`${file}:${lineOf(node.start)} ${src.slice(node.start, Math.min(node.end, node.start + 110))}`);
    }
  });
  edits.forEach((e) => keys.add(e[3]));
  if (report) {
    for (const e of edits.filter((x) => x[4])) console.log(`${file}:${e[4]}  ${JSON.stringify(e[3])}  ⇐ ${src.split('\n')[e[4] - 1].trim().slice(0, 120)}`);
    templates.forEach((x) => console.log(`TEMPLATE ${x}`));
  }
  if (write) {
    let out = src;
    for (const [s, e, rep] of edits.sort((a, b) => b[0] - a[0])) out = out.slice(0, s) + rep + out.slice(e);
    writeFileSync(file, out);
  }
  console.error(`${file}: ${edits.length} edits, ${templates.length} templates`);
}
if (args.includes('--keys')) console.log(JSON.stringify([...keys], null, 0));
