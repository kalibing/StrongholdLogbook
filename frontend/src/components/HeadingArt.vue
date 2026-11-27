<script setup lang="ts">
// 页头右侧的动态背景，参照卫戍协议游戏内的视觉：
// - 结算页「模拟完成」：近黑的青色底、地形等高线、橙色雷达靶环 + 十字准星；
// - 战斗 HUD：薄荷青的圆形节点链、角标框；
// - 隐藏首领警报：红色横向撕裂条一闪而过，靶环同时抖一下。
// 节奏：首次进入时靶环描边、准星伸出、角标锁定；之后雷达扫过的位置点亮回波；
// 切换页面时角标重新锁定一次。只动 transform / opacity / stroke-dashoffset；
// 系统开启「减少动态效果」时整体静止。
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

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
/** 雷达转一圈的秒数；回波的延迟按角度折算，正好在扫描线经过时亮起。 */
const SWEEP = 6
const contours = [
  ...[38, 70, 104, 140, 178, 218].map((radius, index) => contour(TARGET.x - 20, TARGET.y + 6, radius, 1.7 + index * .45)),
  ...[26, 52, 80].map((radius, index) => contour(250, 30, radius, 4.1 + index * .6, .55)),
]
const ticks = Array.from({ length: 24 }, (_, index) => index * 15)
const nodes = [0, 1, 2, 3, 4]
// SVG 角度：从 +x 轴顺时针（y 轴向下），与 rotate() 的正方向一致。
const blips = [[34, 58], [118, 40], [196, 70], [252, 34], [318, 66]].map(([angle, radius]) => ({
  x: TARGET.x + radius * Math.cos(angle * Math.PI / 180),
  y: TARGET.y + radius * Math.sin(angle * Math.PI / 180),
  delay: `${(angle / 360) * SWEEP}s`,
}))
const sweepEdge = { x: TARGET.x + 86, y: TARGET.y }
const sweepTail = { x: TARGET.x + 86 * Math.cos(Math.PI / 3), y: TARGET.y - 86 * Math.sin(Math.PI / 3) }

// 换页时重新挂载角标，让「锁定」动画再播一遍；首次挂载走完整的入场。
const route = useRoute()
const lock = ref(0)
watch(() => route.path, () => { lock.value += 1 })
</script>

<template>
  <div class="hero-art" aria-hidden="true" :style="{ '--sweep': `${SWEEP}s` }">
    <svg class="hero-svg" viewBox="0 0 800 200" preserveAspectRatio="xMaxYMid slice">
      <defs>
        <linearGradient id="hero-sweep-fill" gradientUnits="userSpaceOnUse"
          :x1="sweepTail.x" :y1="sweepTail.y" :x2="sweepEdge.x" :y2="sweepEdge.y">
          <stop offset="0" style="stop-color: var(--target); stop-opacity: 0" />
          <stop offset="1" style="stop-color: var(--target); stop-opacity: .34" />
        </linearGradient>
        <radialGradient id="hero-glow">
          <stop offset="0" style="stop-color: var(--target); stop-opacity: .3" />
          <stop offset="1" style="stop-color: var(--target); stop-opacity: 0" />
        </radialGradient>
      </defs>

      <g class="hero-contours">
        <path v-for="(d, index) in contours" :key="index" :d="d" />
      </g>

      <!-- 橙色雷达靶环；外层 g 负责警报时的抖动 -->
      <g class="hero-jolt">
        <g class="hero-target">
          <circle class="hero-glow" :cx="TARGET.x" :cy="TARGET.y" r="92" />
          <g class="hero-sweep">
            <path class="hero-sweep-fill" :d="`M${TARGET.x},${TARGET.y} L${sweepEdge.x},${sweepEdge.y} A86,86 0 0,0 ${sweepTail.x},${sweepTail.y} Z`" />
            <line class="hero-sweep-edge" :x1="TARGET.x" :y1="TARGET.y" :x2="sweepEdge.x" :y2="sweepEdge.y" />
          </g>
          <circle class="hero-ring hero-ring--faint hero-draw" :cx="TARGET.x" :cy="TARGET.y" r="86" pathLength="1" />
          <g class="hero-ring-ticks">
            <line v-for="angle in ticks" :key="angle" :x1="TARGET.x + 64" :y1="TARGET.y" :x2="TARGET.x + (angle % 90 === 0 ? 74 : 69)" :y2="TARGET.y"
              :transform="`rotate(${angle} ${TARGET.x} ${TARGET.y})`" />
          </g>
          <circle class="hero-ring hero-ring--dashed" :cx="TARGET.x" :cy="TARGET.y" r="48" />
          <circle class="hero-ring hero-draw hero-draw--inner" :cx="TARGET.x" :cy="TARGET.y" r="26" pathLength="1" />
          <circle class="hero-ping" :cx="TARGET.x" :cy="TARGET.y" r="26" />
          <circle class="hero-ping hero-ping--late" :cx="TARGET.x" :cy="TARGET.y" r="26" />
          <circle v-for="(blip, index) in blips" :key="index" class="hero-blip" :cx="blip.x" :cy="blip.y" r="2.6"
            :style="{ animationDelay: blip.delay, transformOrigin: `${blip.x}px ${blip.y}px` }" />
          <circle class="hero-core" :cx="TARGET.x" :cy="TARGET.y" r="5" />
          <g class="hero-crosshair">
            <line :x1="TARGET.x - 32" :y1="TARGET.y" :x2="TARGET.x - 104" :y2="TARGET.y" pathLength="1" />
            <line :x1="TARGET.x + 32" :y1="TARGET.y" :x2="TARGET.x + 104" :y2="TARGET.y" pathLength="1" />
            <line :x1="TARGET.x" :y1="TARGET.y - 32" :x2="TARGET.x" :y2="TARGET.y - 96" pathLength="1" />
            <line :x1="TARGET.x" :y1="TARGET.y + 32" :x2="TARGET.x" :y2="TARGET.y + 96" pathLength="1" />
          </g>
        </g>
      </g>

      <!-- 薄荷青 HUD：靶环角标框 + 节点链 -->
      <g class="hero-hud">
        <g :key="lock" class="hero-lock">
          <path class="hero-bracket" :d="`M${TARGET.x - 120},${TARGET.y - 58} v-14 h18 M${TARGET.x + 120},${TARGET.y - 58} v-14 h-18 M${TARGET.x - 120},${TARGET.y + 58} v14 h18 M${TARGET.x + 120},${TARGET.y + 58} v14 h-18`" />
        </g>
        <line class="hero-chain-line" x1="330" y1="168" x2="450" y2="168" />
        <g v-for="index in nodes" :key="index">
          <circle class="hero-node" :cx="330 + index * 30" cy="168" r="5.5" />
          <circle class="hero-node-fill" :cx="330 + index * 30" cy="168" r="3.4" :style="{ animationDelay: `${index * .3}s` }" />
        </g>
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
  /* 警报周期：撕裂条与靶环抖动共用，保证同一帧发生。 */
  --alarm: 12s;
  --alarm-delay: 3.2s;
  position: absolute; inset: 0 0 0 37%; overflow: hidden; pointer-events: none;
  mask-image: linear-gradient(90deg, transparent, #000 30%);
}
:root[data-theme='light'] .hero-art { --hud: #1d8f7b; --target: #c8701c; --alert: #c8302d; }
/* 浅色底上橙色光晕和扫描扇形显得太重，压一压。 */
:root[data-theme='light'] .hero-svg :is(.hero-glow, .hero-sweep-fill) { opacity: .55; }

.hero-svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.hero-svg :is(path, line, circle) { fill: none; vector-effect: non-scaling-stroke; }
.hero-svg .hero-glow { fill: url(#hero-glow); stroke: none; }
.hero-svg .hero-sweep-fill { fill: url(#hero-sweep-fill); stroke: none; }
.hero-sweep-edge { stroke: color-mix(in srgb, var(--target) 85%, transparent); stroke-width: 1.2; }

.hero-contours path { stroke: color-mix(in srgb, var(--hud) 15%, transparent); stroke-width: 1; }

.hero-ring { stroke: var(--target); stroke-width: 1.4; }
.hero-ring--faint { stroke: color-mix(in srgb, var(--target) 35%, transparent); stroke-width: 1; }
.hero-ring--dashed { stroke: color-mix(in srgb, var(--target) 75%, transparent); stroke-dasharray: 10 7; }
.hero-ring-ticks line { stroke: color-mix(in srgb, var(--target) 55%, transparent); stroke-width: 1; }
.hero-ping { stroke: var(--target); stroke-width: 1.2; opacity: 0; }
.hero-svg .hero-blip { fill: var(--target); stroke: none; opacity: 0; }
.hero-svg .hero-core { fill: var(--target); stroke: none; }
.hero-crosshair line { stroke: color-mix(in srgb, var(--target) 50%, transparent); stroke-width: 1; }

.hero-bracket { stroke: var(--hud); stroke-width: 1.4; opacity: .8; }
.hero-chain-line { stroke: color-mix(in srgb, var(--hud) 40%, transparent); stroke-width: 1; }
.hero-svg .hero-node { stroke: var(--hud); stroke-width: 1.2; fill: color-mix(in srgb, var(--hud) 10%, transparent); }
.hero-svg .hero-node-fill { fill: var(--hud); stroke: none; opacity: .15; }
.hero-pointer { stroke: color-mix(in srgb, var(--hud) 55%, transparent); stroke-width: 1.2; stroke-dasharray: 4 5; }

/* 围绕靶心旋转 / 缩放：SVG 元素以 viewBox 坐标作变换原点。 */
.hero-sweep, .hero-ring--dashed, .hero-ring-ticks, .hero-ping, .hero-lock, .hero-target, .hero-jolt {
  transform-box: view-box; transform-origin: 590px 100px;
}
.hero-blip { transform-box: view-box; }

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
  /* —— 入场：靶环描边 → 准星伸出 → 角标锁定，约 1.2 秒 —— */
  .hero-target { animation: hero-fade .5s ease-out both; }
  .hero-draw { stroke-dasharray: 1; animation: hero-draw .9s cubic-bezier(.6, 0, .2, 1) .1s both; }
  .hero-draw--inner { animation-delay: .35s; animation-duration: .6s; }
  .hero-crosshair line { stroke-dasharray: 1; animation: hero-draw .5s cubic-bezier(.3, 0, .2, 1) .55s both; }
  .hero-ring--dashed { animation: hero-fade .4s ease-out .45s both, hero-spin 22s linear infinite reverse; }
  .hero-ring-ticks { animation: hero-fade .4s ease-out .6s both, hero-spin 48s linear infinite; }
  .hero-lock { animation: hero-lock .55s cubic-bezier(.2, .8, .2, 1) .75s both; }
  .hero-chain-line { stroke-dasharray: 120; animation: hero-chain .6s ease-out .3s both; }

  /* —— 常驻循环 —— */
  .hero-contours { animation: hero-contours 24s ease-in-out infinite alternate; }
  .hero-sweep { animation: hero-spin var(--sweep) linear infinite; }
  .hero-blip { animation: hero-blip var(--sweep) ease-out infinite; }
  .hero-ping { animation: hero-ping 3.6s cubic-bezier(.2, .6, .3, 1) 1.2s infinite; }
  .hero-ping--late { animation-delay: 3s; }
  .hero-core { animation: hero-blink 2s ease-in-out infinite; }
  .hero-bracket { animation: hero-bracket 4s ease-in-out 1.3s infinite; }
  .hero-node-fill { animation: hero-node 3s ease-in-out infinite; }
  .hero-pointer { animation: hero-dash 1.6s linear infinite; }

  /* —— 警报：撕裂条与靶环抖动同步 —— */
  .hero-glitch { animation: hero-glitch var(--alarm) steps(1, end) var(--alarm-delay) infinite; }
  .hero-glitch--b { animation-delay: calc(var(--alarm-delay) + .06s); }
  .hero-glitch--c { animation-delay: calc(var(--alarm-delay) + .12s); }
  .hero-jolt { animation: hero-jolt var(--alarm) steps(1, end) var(--alarm-delay) infinite; }
}

@keyframes hero-fade { from { opacity: 0; } }
@keyframes hero-draw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
@keyframes hero-chain { from { stroke-dashoffset: 120; } to { stroke-dashoffset: 0; } }
/* 角标从外圈收拢，过冲一点再停住，像准星咬住目标。 */
@keyframes hero-lock {
  0% { opacity: 0; transform: scale(1.45); }
  55% { opacity: 1; transform: scale(.94); }
  75% { transform: scale(1.03); }
  100% { opacity: 1; transform: scale(1); }
}
@keyframes hero-contours { from { transform: translateX(0); } to { transform: translateX(-22px); } }
@keyframes hero-spin { to { transform: rotate(360deg); } }
/* 扫描线经过时亮起，随后余辉慢慢退掉。 */
@keyframes hero-blip {
  0% { opacity: .95; transform: scale(1.6); }
  12% { opacity: .7; transform: scale(1); }
  60%, 100% { opacity: 0; transform: scale(1); }
}
@keyframes hero-ping { 0% { opacity: .7; transform: scale(1); } 100% { opacity: 0; transform: scale(3.2); } }
@keyframes hero-blink { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
@keyframes hero-bracket { 0%, 100% { opacity: .85; } 50% { opacity: .4; } }
/* 节点依次点亮，形成从左到右流过的信号。 */
@keyframes hero-node { 0%, 100% { opacity: .15; } 18% { opacity: .9; } 40% { opacity: .15; } }
@keyframes hero-dash { to { stroke-dashoffset: -18; } }
/* 一个周期里只在开头约 0.6 秒闪几下：位移 + 透明度，像信号被撕开。 */
@keyframes hero-glitch {
  0% { opacity: .9; transform: translateX(0); }
  1% { opacity: 0; }
  1.7% { opacity: .75; transform: translateX(-14px); }
  2.5% { opacity: .5; transform: translateX(9px) scaleY(1.6); }
  3.3% { opacity: .85; transform: translateX(-4px); }
  4.6%, 100% { opacity: 0; transform: translateX(0); }
}
@keyframes hero-jolt {
  0% { transform: translateX(3px); }
  1.7% { transform: translateX(-5px); }
  2.5% { transform: translateX(2px); }
  3.3% { transform: translateX(-1px); }
  4.6%, 100% { transform: none; }
}
</style>
