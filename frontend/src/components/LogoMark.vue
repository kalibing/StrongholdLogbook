<script setup lang="ts">
// 站点标志，取自卫戍协议战术终端的视觉语言（与页头动效呼应）：
// - 四角锁定框：HUD 的目标锁定角标，主色；
// - 菱形据点：卫戍 / 守备的阵地，薄荷青描边，四个顶点向外伸出准星刻度；
// - 实心核心：被守住的据点，主色。
// 原创图形，不使用游戏官方标志；颜色取站点变量，跟随光暗主题。
withDefaults(defineProps<{ size?: number }>(), { size: 30 })
</script>

<template>
  <svg class="logo-mark" :width="size" :height="size" viewBox="0 0 32 32" aria-hidden="true">
    <path class="logo-mark-lock" d="M3 9.5V3h6.5M22.5 3H29v6.5M29 22.5V29h-6.5M9.5 29H3v-6.5" />
    <path class="logo-mark-fort" d="M16 7.5L24.5 16 16 24.5 7.5 16z" />
    <path class="logo-mark-ticks" d="M16 4.5v3M27.5 16h-3M16 27.5v-3M4.5 16h3" />
    <path class="logo-mark-core" d="M16 12.4L19.6 16 16 19.6 12.4 16z" />
  </svg>
</template>

<style scoped>
.logo-mark { flex: none; display: block; color: var(--accent); }
.logo-mark path { stroke-linecap: square; stroke-linejoin: miter; }
.logo-mark-lock { fill: none; stroke: currentColor; stroke-width: 2; }
.logo-mark-fort { fill: color-mix(in srgb, var(--hud) 12%, transparent); stroke: var(--hud); stroke-width: 1.8; }
.logo-mark-ticks { fill: none; stroke: var(--hud); stroke-width: 1.6; opacity: .7; }
.logo-mark-core { fill: currentColor; }
</style>
