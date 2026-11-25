import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

const KEY = 'bs-theme'

export const useThemeStore = defineStore('theme', () => {
  const saved = localStorage.getItem(KEY)
  // 产品偏好：默认暗色；只有用户显式保存过 light 才用亮色。
  const mode = ref(saved === 'light' ? 'light' : 'dark')

  function apply() {
    const el = document.documentElement
    el.classList.toggle('dark', mode.value === 'dark')
    el.classList.toggle('light', mode.value === 'light')
    el.dataset.theme = mode.value
  }
  apply()

  function setMode(next) {
    mode.value = next === 'light' ? 'light' : 'dark'
  }

  function toggle(event) {
    const next = mode.value === 'dark' ? 'light' : 'dark'
    const root = document.documentElement
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    if (!document.startViewTransition || reduce) {
      mode.value = next
      return
    }
    const x = event?.clientX ?? window.innerWidth / 2
    const y = event?.clientY ?? 60
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
    root.style.setProperty('--theme-x', `${x}px`)
    root.style.setProperty('--theme-y', `${y}px`)
    root.style.setProperty('--theme-r', `${radius}px`)
    root.classList.add('theme-animating')
    try {
      const transition = document.startViewTransition(() => {
        mode.value = next
        apply()
      })
      transition.finished.finally(() => root.classList.remove('theme-animating'))
    } catch {
      root.classList.remove('theme-animating')
      mode.value = next
    }
  }

  watch(mode, (v) => {
    localStorage.setItem(KEY, v)
    apply()
  })

  const isDark = computed(() => mode.value === 'dark')
  return { mode, isDark, toggle, setMode }
})
