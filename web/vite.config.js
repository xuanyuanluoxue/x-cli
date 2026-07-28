// Vite config — x-cli web console
//
// 构建产物直接输出到 Python 包的静态目录 core/web/static/，
// 由 core/web/server.py 以 ``Cache-Control: no-store`` 服务。
// base 用相对路径 './'，保证从任何挂载路径（默认 /）都能加载 hashed assets。

import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  base: "./",
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "../core/web/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // 开发时代理到本地 x web 服务（先跑 `x web --port 8421 --no-browser`）
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8421",
        changeOrigin: false,
      },
    },
  },
});
