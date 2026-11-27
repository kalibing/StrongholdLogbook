import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址可用 LOGBOOK_API_TARGET 覆盖（默认 8000；端口被占用时改端口无需改代码）
const apiTarget = process.env.LOGBOOK_API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': apiTarget } },
})
