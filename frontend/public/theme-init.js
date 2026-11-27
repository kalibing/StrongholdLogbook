// 首屏前确定主题，避免闪烁。放在外部文件里，CSP 无需放行内联脚本。
try {
  document.documentElement.dataset.theme = localStorage.getItem('logbook:theme') === 'light' ? 'light' : 'dark'
} catch (error) {
  document.documentElement.dataset.theme = 'dark'
}
