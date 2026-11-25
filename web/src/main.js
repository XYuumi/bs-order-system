import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/theme-chalk/dark/css-vars.css'
// 函数式组件不经过模板解析，样式在此显式引入；其余组件样式由 unplugin 按需注入
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { addIcon } from '@iconify/vue'
import riIcons from '@iconify-json/ri/icons.json'
import './styles/base.css'

import App from './App.vue'
import router from './router'

// Remix Icon 按需注册：构建时已把图标集裁剪为源码实际用到的图标
// 注意 icons.json 里每个图标只有 body，宽高/偏移在集合根节点（24×24），
// 必须补齐，否则 Iconify 默认按 16×16 viewBox 渲染，路径会被放大后裁切。
for (const [name, data] of Object.entries(riIcons.icons)) {
  const icon = {
    ...data,
    width: data.width || riIcons.width || 24,
    height: data.height || riIcons.height || 24,
  }
  if (icon.left == null && riIcons.left != null) icon.left = riIcons.left
  if (icon.top == null && riIcons.top != null) icon.top = riIcons.top
  addIcon(`ri:${name}`, icon)
}

dayjs.locale('zh-cn')

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
