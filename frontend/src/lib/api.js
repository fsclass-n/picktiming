import { handleMock } from './mock.js';

// API 주소: 서버가 응답한 /js/config.js(EC2·로컬 풀스택 = "/") → 빌드 시 주입한 VITE_API_URL(Render Static Site) 순서로 사용
const BASE = (window.APP_CONFIG?.API_BASE_URL || import.meta.env.VITE_API_URL || '').trim();
/** 둘 다 없으면 데모 모드(Netlify): 같은 REST 계약을 브라우저 목업으로 처리 */
export const DEMO = BASE === '';
const API_ROOT = `${BASE.replace(/\/+$/, '')}/api/v1`;
const TOKEN_KEY = 'pt_token';
const USER_KEY = 'pt_user';

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export const auth = {
  token: () => localStorage.getItem(TOKEN_KEY),
  user: () => {
    try {
      const value = JSON.parse(localStorage.getItem(USER_KEY) || 'null');
      return value && typeof value === 'object' && value.id != null && ['USER', 'ADMIN'].includes(value.role) ? value : null;
    } catch {
      localStorage.removeItem(USER_KEY);
      localStorage.removeItem(TOKEN_KEY);
      return null;
    }
  },
  save(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

async function request(method, path, body) {
  const token = auth.token();
  if (DEMO) {
    const res = await handleMock(method, path, body, token);
    if (res.status >= 400) throw new ApiError(res.status, res.body.code, res.body.message);
    return res.body;
  }
  let resp;
  try {
    resp = await fetch(API_ROOT + path, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', 'API 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
  }
  const data = resp.status === 204 ? null : await resp.json().catch(() => ({}));
  if (resp.status === 401 && !path.startsWith('/auth/')) {
    auth.clear();
    window.dispatchEvent(new Event('pt:logout'));
  }
  if (!resp.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : null;
    throw new ApiError(resp.status, data?.code, data?.message || detail || (resp.status === 422 ? '입력 형식을 확인해 주세요.' : `요청 실패 (${resp.status})`));
  }
  return data;
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body = {}) => request('POST', path, body),
  patch: (path, body = {}) => request('PATCH', path, body),
  del: (path) => request('DELETE', path),
};

/** 소셜 로그인 시작 주소 (서버가 제공자 로그인 화면으로 이동시킴) */
export const oauthStartUrl = (provider, next = '/') => `${BASE.replace(/\/+$/, '')}/api/v1/auth/oauth/${provider}/start?next=${encodeURIComponent(next)}`;
