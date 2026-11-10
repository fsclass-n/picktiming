import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// API 주소 결정 순서 (src/lib/api.js)
//   1) 서버가 응답한 /js/config.js의 API_BASE_URL — EC2(nginx)·로컬 풀스택(FastAPI)은 같은 도메인 "/"
//   2) 빌드 시 주입한 VITE_API_URL — Render Static Site(예: https://timepick-ai.onrender.com)
//   3) 둘 다 없으면 데모 모드(브라우저 목업 API) — Netlify
// 커밋되는 public/js/config.js는 데모 모드("")라서 VITE_API_URL이 있으면 2)가 적용된다.

/** VITE_API_URL 검증: http(s) 전체 주소만 허용하고 끝의 / 를 정리한다. 잘못된 값은 빌드를 실패시켜 화면이 조용히 데모로 바뀌는 것을 막는다 */
function resolveApiUrl(env) {
  if (env.VITE_DEMO) return '';
  const raw = (env.VITE_API_URL || '').trim();
  if (!raw) return '';
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`VITE_API_URL은 https://로 시작하는 전체 주소여야 합니다: "${raw}"`);
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.search || url.hash) {
    throw new Error(`VITE_API_URL은 쿼리·해시 없는 http(s) 주소여야 합니다: "${raw}"`);
  }
  return `${url.origin}${url.pathname}`.replace(/\/+$/, '');
}

// 개발 서버(npm run dev): /api·/health는 로컬 FastAPI(8000)로 프록시하고, /js/config.js는 같은 도메인 설정을 돌려준다.
// VITE_API_URL을 지정하면 그 주소(예: 배포된 백엔드)를, VITE_DEMO=1이면 데모 모드를 쓰도록 config.js를 비워 둔다.
const devConfig = (apiUrl, demo) => ({
  name: 'dev-api-config',
  configureServer(server) {
    server.middlewares.use('/js/config.js', (req, res) => {
      res.setHeader('Content-Type', 'application/javascript');
      res.end(`window.APP_CONFIG = { API_BASE_URL: "${demo || apiUrl ? '' : '/'}" };`);
    });
  },
});

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), 'VITE_'), ...process.env };
  const apiUrl = resolveApiUrl(env);
  return {
    plugins: [react(), tailwindcss(), devConfig(apiUrl, Boolean(env.VITE_DEMO))],
    define: { 'import.meta.env.VITE_API_URL': JSON.stringify(apiUrl) },
    server: {
      port: 5173,
      proxy: { '/api': 'http://localhost:8000', '/health': 'http://localhost:8000', '/docs': 'http://localhost:8000', '/openapi.json': 'http://localhost:8000' },
    },
    build: { outDir: 'dist', chunkSizeWarningLimit: 900 },
  };
});
