import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import './i18n';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 60_000, retry: 1 },
    mutations: { retry: 0 },
  },
});

// 构建标记：写入全局，便于线上核对「浏览器到底加载到哪一版」。
// 2026-09-07 曾因 CDN 把 HTML 缓存到 .js 的 URL 上导致 React 白屏，
// 有这个标记就能一眼区分是部署没生效还是缓存/回退问题（控制台输入 __HL_BUILD__ 查看）。
window.__HL_BUILD__ = '20261023a';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* P0-3（2026-10-23）：全局 ErrorBoundary——任一页面渲染异常不再让整站白屏，
        展示友好提示 + 刷新按钮 + 错误详情。 */}
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        {/* basename 与 vite base('/app/') 对齐；本地 dev 时为 '' */}
        <BrowserRouter basename={(import.meta.env.BASE_URL || '/').replace(/\/$/, '')}>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
