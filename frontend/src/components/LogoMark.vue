<script setup lang="ts">
// 站点标志：切角盾形描边（卫戍 / 守备）+ 实心三角（方舟贯穿始终的三角符号）+ 底座横条（据点）。
// 原创图形，不使用游戏官方标志；颜色取 currentColor，跟随主色与光暗主题。
withDefaults(defineProps<{ size?: number }>(), { size: 30 })
</script>

<template>
  <svg class="logo-mark" :width="size" :height="size" viewBox="0 0 32 32" aria-hidden="true">
    <path class="logo-mark-shield" d="M7 2.5h18l4 4V18L16 29.5 3 18V6.5z" />
    <path class="logo-mark-tri" d="M16 8.5l6.2 10.5H9.8z" />
    <rect class="logo-mark-base" x="11" y="21" width="10" height="2" />
    <path class="logo-mark-notch" d="M25 2.5l4 4" />
  </svg>
</template>

<style scoped>
.logo-mark { flex: none; display: block; color: var(--accent); }
.logo-mark-shield { fill: color-mix(in srgb, currentColor 10%, transparent); stroke: currentColor; stroke-width: 2; stroke-linejoin: miter; }
.logo-mark-tri, .logo-mark-base { fill: currentColor; }
.logo-mark-notch { stroke: var(--text); stroke-width: 2; opacity: .85; }
</style>
