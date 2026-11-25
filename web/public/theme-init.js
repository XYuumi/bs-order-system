/* 首屏主题引导：必须在样式与 Vue 挂载前执行，否则亮色用户会先闪一帧暗色。
   独立文件而非内联脚本，以满足 script-src 'self' 的 CSP。 */
;(function () {
  try {
    var saved = localStorage.getItem('bs-theme')
    var mode = saved === 'light' ? 'light' : 'dark'
    var el = document.documentElement
    el.classList.add(mode)
    el.dataset.theme = mode
    el.style.colorScheme = mode
  } catch (e) {}
})()
