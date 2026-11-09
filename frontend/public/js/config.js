// API 주소. 비어 있으면 빌드 시 주입한 VITE_API_URL(Render Static Site)을 쓰고, 그것도 없으면 데모 모드(Netlify).
// EC2(nginx)·로컬 풀스택(FastAPI)은 이 경로를 API_BASE_URL: "/"(같은 도메인)로 바꿔 응답한다. 이 파일은 ""로 유지한다.
window.APP_CONFIG = { API_BASE_URL: "" };
