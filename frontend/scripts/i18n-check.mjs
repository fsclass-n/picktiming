// 영어 사전 누락 검사: 화면 코드의 t('…') 원문이 src/lib/i18n-en.js에 모두 있는지 확인한다 (npm run i18n:check, CI에서 실행)
// 새 한국어 문구를 추가했다면: node scripts/i18n-wrap.mjs --report <파일> 로 t()로 감쌀 곳을 찾고, 영어 사전에 번역을 넣는다.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import EN from '../src/lib/i18n-en.js';

const CALL = /\bt\(\s*(['"])((?:\\.|(?!\1).)*)\1/g;
const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path);
    else if (/\.(jsx?|mjs)$/.test(name) && !name.startsWith('i18n')) files.push(path);
  }
})('src');

const missing = new Set();
let total = 0;
for (const file of files) {
  for (const m of readFileSync(file, 'utf8').matchAll(CALL)) {
    total += 1;
    const key = JSON.parse(`"${m[2].replace(/\\'/g, "'").replace(/"/g, '\\"')}"`);
    if (!(key in EN)) missing.add(`${file}: ${key}`);
  }
}
if (missing.size) {
  console.error(`영어 번역이 없는 문구 ${missing.size}개:\n${[...missing].join('\n')}`);
  process.exit(1);
}
console.log(`i18n OK — t() ${total}곳, 사전 ${Object.keys(EN).length}개`);
