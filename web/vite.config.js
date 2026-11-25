import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)))
const srcDir = path.resolve(projectRoot, 'src')

// 构建时扫描源码里的 ri:xxx 图标名，只保留实际用到的 Remix Icon，
// 避免整包 3000+ 图标（约 1 MB JSON）被打进首屏；新增图标后重新构建即可。
function riIconsOnDemand() {
  let isBuild = false
  return {
    name: 'ri-icons-on-demand',
    enforce: 'pre',
    configResolved(config) {
      isBuild = config.command === 'build'
    },
    load(id) {
      if (!isBuild) return
      const file = id.split('?')[0]
      // 只处理图标包本身。id 是 Vite 解析后的路径：node_modules 若是软链（或项目目录本身经过软链），
      // 它不会落在 projectRoot 之下，所以不能按「项目目录」前缀判断——否则会悄悄跳过裁剪，把整包图标打进去。
      if (!file.replace(/\\/g, '/').endsWith('@iconify-json/ri/icons.json')) return

      const collection = JSON.parse(fs.readFileSync(file, 'utf8'))
      const used = new Set()
      // 按不区分大小写的字母序扫描（与 Windows 目录顺序一致）：不同操作系统的目录返回顺序不同，
      // 不排序会让图标排列顺序随平台变化，入口文件哈希随之变化，构建结果无法跨平台复现。
      const byName = (a, b) => {
        const ua = a.name.toUpperCase()
        const ub = b.name.toUpperCase()
        return ua < ub ? -1 : ua > ub ? 1 : 0
      }
      const walk = (dir) => {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort(byName)) {
          const current = path.resolve(dir, entry.name)
          // 只扫描 src 目录内的文件，越界的一律跳过
          if (!current.startsWith(srcDir + path.sep)) continue
          if (entry.isDirectory()) {
            walk(current)
          } else if (/\.(vue|js|ts)$/.test(entry.name)) {
            for (const match of fs.readFileSync(current, 'utf8').matchAll(/ri:[a-z0-9-]+/g)) {
              used.add(match[0].slice(3))
            }
          }
        }
      }
      walk(srcDir)

      const icons = {}
      for (const name of used) {
        if (collection.icons[name]) icons[name] = collection.icons[name]
      }
      return JSON.stringify({ ...collection, icons, aliases: {} })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // 后端地址默认与 .env.example 的 PORT=8000 一致；端口不同时在 web/.env.local 里写 VITE_API_ORIGIN=http://127.0.0.1:端口
  const apiOrigin = env.VITE_API_ORIGIN || 'http://127.0.0.1:8000'
  const wsOrigin = apiOrigin.replace(/^http/, 'ws')

  return {
    plugins: [
      vue(),
      // Element Plus 按需引入：模板组件、v-loading 指令与 ElMessage 等函数式 API 均自动解析
      AutoImport({ resolvers: [ElementPlusResolver()], dts: false }),
      Components({ resolvers: [ElementPlusResolver()], dts: false }),
      riIconsOnDemand(),
    ],
    server: {
      port: 5173,
      proxy: {
        // 注意带尾斜杠：只代理 /api/xxx，避免误伤以 /api 开头的前端路由（如 /api-docs）
        '/api/': {
          target: apiOrigin,
          changeOrigin: true,
        },
        // WebSocket 实时推送
        '/ws': {
          target: wsOrigin,
          ws: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      chunkSizeWarningLimit: 1500,
      rollupOptions: {
        output: {
          manualChunks: {
            echarts: ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'],
            vendor: ['vue', 'vue-router', 'pinia', 'axios', '@iconify/vue', 'marked', 'dompurify'],
          },
        },
      },
    },
  }
})
