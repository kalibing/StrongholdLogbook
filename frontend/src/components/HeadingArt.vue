<script setup lang="ts">
// 页头右侧的动态背景，参照卫戍协议游戏内的视觉：
// - 结算页「模拟完成」：近黑的青色底、地形等高线、橙色雷达靶环 + 十字准星；
// - 战斗 HUD：薄荷青的圆形节点链、角标框；
// - 隐藏首领警报：红色横向撕裂条一闪而过。
// 只动 transform / opacity；系统开启「减少动态效果」时整体静止。

/** 不规则的闭合等高线：在椭圆上叠两组正弦扰动，种子不同形状就不同。 */
function contour(cx: number, cy: number, radius: number, seed: number, squash = .62): string {
  const steps = 72
  const points = Array.from({ length: steps }, (_, index) => {
    const angle = (index / steps) * Math.PI * 2
    const wobble = 1 + .13 * Math.sin(3 * angle + seed) + .07 * Math.sin(5 * angle + seed * 2.3)
    const x = cx + Math.cos(angle) * radius * wobble
    const y = cy + Math.sin(angle) * radius * wobble * squash
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return `M${points.join('L')}Z`
}

const TARGET = { x: 590, y: 100 }
const contours = [
  ...[38, 70, 104, 140, 178, 218].map((radius, index) => contour(TARGET.x - 20, TARGET.y + 6, radius, 1.7 + index * .45)),
  ...[26, 52, 80].map((radius, index) => contour(250, 30, radius, 4.1 + index * .6, .55)),
]
const ticks = Array.from({ length: 24 }, (_, index) => index * 15)
const nodes = [0, 1, 2, 3, 4]
</script>

<template>
  <div class="hero-art" aria-hidden="true">
    <svg class="hero-svg" viewBox="0 0 800 200" preserveAspectRatio="xMaxYMid slice">
      <defs>
        <linearGradient id="hero-sweep-fill" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" style="stop-color: var(--target); stop-opacity: 0" />
          <stop offset="1" style="stop-color: var(--target); stop-opacity: .38" />
        </linearGradient>
        <radialGradient id="hero-glow">
          <stop offset="0" style="stop-color: var(--target); stop-opacity: .3" />
          <stop offset="1" style="stop-color: var(--target); stop-opacity: 0" />
        </radialGradient>
      </defs>

      <g class="hero-contours">
        <path v-for="(d, index) in contours" :key="index" :d="d" />
      </g>

      <!-- 橙色雷达靶环 -->
      <g class="hero-target">
        <circle class="hero-glow" :cx="TARGET.x" :cy="TARGET.y" r="92" />
        <path class="hero-sweep" :d="`M${TARGET.x},${TARGET.y} L${TARGET.x + 86},${TARGET.y} A86,86 0 0,0 ${TARGET.x + 86 * Math.cos(Math.PI / 3)},${TARGET.y - 86 * Math.sin(Math.PI / 3)} Z`" />
        <circle class="hero-ring hero-ring--faint" :cx="TARGET.x" :cy="TARGET.y" r="86" />
        <g class="hero-ring-ticks">
          <line v-for="angle in ticks" :key="angle" :x1="TARGET.x + 64" :y1="TARGET.y" :x2="TARGET.x + (angle % 90 === 0 ? 74 : 69)" :y2="TARGET.y"
            :transform="`rotate(${angle} ${TARGET.x} ${TARGET.y})`" />
        </g>
        <circle class="hero-ring hero-ring--dashed" :cx="TARGET.x" :cy="TARGET.y" r="48" />
        <circle class="hero-ring" :cx="TARGET.x" :cy="TARGET.y" r="26" />
        <circle class="hero-ping" :cx="TARGET.x" :cy="TARGET.y" r="26" />
        <circle class="hero-ping hero-ping--late" :cx="TARGET.x" :cy="TARGET.y" r="26" />
        <circle class="hero-core" :cx="TARGET.x" :cy="TARGET.y" r="5" />
        <g class="hero-crosshair">
          <line :x1="TARGET.x - 104" :y1="TARGET.y" :x2="TARGET.x - 32" :y2="TARGET.y" />
          <line :x1="TARGET.x + 32" :y1="TARGET.y" :x2="TARGET.x + 104" :y2="TARGET.y" />
          <line :x1="TARGET.x" :y1="TARGET.y - 96" :x2="TARGET.x" :y2="TARGET.y - 32" />
          <line :x1="TARGET.x" :y1="TARGET.y + 32" :x2="TARGET.x" :y2="TARGET.y + 96" />
        </g>
      </g>

      <!-- 薄荷青 HUD：靶环角标框 + 节点链 -->
      <g class="hero-hud">
        <path class="hero-bracket" :d="`M${TARGET.x - 120},${TARGET.y - 58} v-14 h18 M${TARGET.x + 120},${TARGET.y - 58} v-14 h-18 M${TARGET.x - 120},${TARGET.y + 58} v14 h18 M${TARGET.x + 120},${TARGET.y + 58} v14 h-18`" />
        <line class="hero-chain-line" x1="330" y1="168" x2="450" y2="168" />
        <circle v-for="index in nodes" :key="index" class="hero-node" :cx="330 + index * 30" cy="168" r="5.5"
          :style="{ animationDelay: `${index * .45}s` }" />
        <path class="hero-pointer" :d="`M462,152 L${TARGET.x - 34},${TARGET.y + 18}`" />
      </g>
    </svg>

    <!-- 隐藏首领警报式的红色撕裂条 -->
    <span class="hero-glitch hero-glitch--a"></span>
    <span class="hero-glitch hero-glitch--b"></span>
    <span class="hero-glitch hero-glitch--c"></span>
  </div>
</template>

<style scoped>
.hero-art {
  --hud: #43d8bc;
  --target: #f2a046;
  --alert: #e2433f;
  position: absolute; inset: 0 0 0 37%; overflow: hidden; pointer-events: none;
  mask-image: linear-gradient(90deg, transparent, #000 30%);
}
:root[data-theme='light'] .hero-art { --hud: #1d8f7b; --target: #c8701c; --alert: #c8302d; }

.hero-svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.hero-svg :is(path, line, circle) { fill: none; vector-effect: non-scaling-stroke; }
.hero-svg .hero-glow { fill: url(#hero-glow); stroke: none; }
.hero-svg .hero-sweep { fill: url(#hero-sweep-fill); stroke: none; }

.hero-contours path { stroke: color-mix(in srgb, var(--hud) 15%, transparent); stroke-width: 1; }

.hero-ring { stroke: var(--target); stroke-width: 1.4; }
.hero-ring--faint { stroke: color-mix(in srgb, var(--target) 35%, transparent); stroke-width: 1; }
.hero-ring--dashed { stroke: color-mix(in srgb, var(--target) 75%, transparent); stroke-dasharray: 10 7; }
.hero-ring-ticks line { stroke: color-mix(in srgb, var(--target) 55%, transparent); stroke-width: 1; }
.hero-ping { stroke: var(--target); stroke-width: 1.2; opacity: 0; }
.hero-svg .hero-core { fill: var(--target); stroke: none; }
.hero-crosshair line { stroke: color-mix(in srgb, var(--target) 50%, transparent); stroke-width: 1; }

.hero-bracket { stroke: var(--hud); stroke-width: 1.4; opacity: .8; }
.hero-chain-line { stroke: color-mix(in srgb, var(--hud) 40%, transparent); stroke-width: 1; }
.hero-svg .hero-node { stroke: var(--hud); stroke-width: 1.2; fill: color-mix(in srgb, var(--hud) 12%, transparent); }
.hero-pointer { stroke: color-mix(in srgb, var(--hud) 55%, transparent); stroke-width: 1.2; stroke-dasharray: 4 5; }

/* 围绕靶心旋转：SVG 元素以 viewBox 坐标作变换原点。 */
.hero-sweep, .hero-ring--dashed, .hero-ring-ticks, .hero-ping { transform-box: view-box; transform-origin: 590px 100px; }

.hero-glitch {
  position: absolute; left: 8%; right: 0; opacity: 0;
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--alert) 55%, transparent) 18%,
    color-mix(in srgb, var(--alert) 30%, transparent) 70%, transparent);
  box-shadow: -6px 0 0 color-mix(in srgb, #3fe0ff 18%, transparent), 6px 0 0 color-mix(in srgb, var(--alert) 25%, transparent);
}
.hero-glitch--a { top: 28%; height: 7px; }
.hero-glitch--b { top: 54%; height: 13px; }
.hero-glitch--c { top: 71%; height: 4px; }

@media (max-width: 730px) {
  .hero-art { inset-inline-start: 34%; opacity: .7; }
}

@media (prefers-reduced-motion: no-preference) {
  .hero-contours { animation: hero-contours 16s ease-in-out infinite alternate; }
  .hero-sweep { animation: hero-spin 5.5s linear infinite; }
  .hero-ring--dashed { animation: hero-spin 22s linear infinite reverse; }
  .hero-ring-ticks { animation: hero-spin 40s linear infinite; }
  .hero-ping { animation: hero-ping 3.2s cubic-bezier(.2, .6, .3, 1) infinite; }
  .hero-ping--late { animation-delay: 1.6s; }
  .hero-core { animation: hero-blink 1.6s ease-in-out infinite; }
  .hero-bracket { animation: hero-bracket 4s ease-in-out infinite; }
  .hero-node { animation: hero-node 2.25s ease-in-out infinite; }
  .hero-pointer { animation: hero-dash 1.4s linear infinite; }
  .hero-glitch { animation: hero-glitch 9s steps(1, end) 2s infinite; }
  .hero-glitch--b { animation-delay: 2.06s; }
  .hero-glitch--c { animation-delay: 2.12s; }
}

@keyframes hero-contours { from { transform: translateX(0); } to { transform: translateX(-18px); } }
@keyframes hero-spin { to { transform: rotate(360deg); } }
@keyframes hero-ping { 0% { opacity: .75; transform: scale(1); } 100% { opacity: 0; transform: scale(3.2); } }
@keyframes hero-blink { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
@keyframes hero-bracket { 0%, 100% { opacity: .85; } 50% { opacity: .35; } }
@keyframes hero-node {
  0%, 100% { fill: color-mix(in srgb, var(--hud) 12%, transparent); }
  20% { fill: color-mix(in srgb, var(--hud) 80%, transparent); }
  45% { fill: color-mix(in srgb, var(--hud) 12%, transparent); }
}
@keyframes hero-dash { to { stroke-dashoffset: -18; } }
/* 9 秒里只在开头约 0.5 秒闪几下：位移 + 透明度，像信号被撕开。 */
@keyframes hero-glitch {
  0% { opacity: .9; transform: translateX(0); }
  1.2% { opacity: 0; }
  2% { opacity: .75; transform: translateX(-14px); }
  3% { opacity: .5; transform: translateX(9px) scaleY(1.6); }
  4% { opacity: .85; transform: translateX(-4px); }
  5.5%, 100% { opacity: 0; transform: translateX(0); }
}
</style>
