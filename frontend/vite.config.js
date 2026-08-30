import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/metrics': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  // 部署到 Cloudflare Pages 的 /app/ 子路径：
  // 根路径 / 保留给内容型 GEO 首页（SEO 主资产），SPA 不能顶替它。
  base: '/app/',
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
