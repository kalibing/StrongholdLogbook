<script setup lang="ts">
// 页头右侧的动态背景：网格缓慢平移、三层斜切面板错速漂移、周期性扫描光、中心菱形信号向外脉冲、零星光点上浮。
// 只动 transform / opacity，不触发重排；系统开启「减少动态效果」时整体静止。
const sparks = [
  { left: '18%', delay: '0s', duration: '9s', size: '3px' },
  { left: '34%', delay: '2.6s', duration: '11s', size: '2px' },
  { left: '52%', delay: '5.1s', duration: '8.5s', size: '3px' },
  { left: '67%', delay: '1.3s', duration: '10s', size: '2px' },
  { left: '81%', delay: '3.8s', duration: '12s', size: '3px' },
  { left: '93%', delay: '6.4s', duration: '9.5s', size: '2px' },
]
</script>

<template>
  <div class="hero-art" aria-hidden="true">
    <div class="hero-grid"></div>
    <div class="hero-panels">
      <span class="hero-panel hero-panel--back"></span>
      <span class="hero-panel hero-panel--middle"></span>
      <span class="hero-panel hero-panel--front"></span>
      <div class="hero-mark">
        <i class="hero-ping"></i>
        <i class="hero-ping hero-ping--late"></i>
        <span class="hero-core"></span>
      </div>
    </div>
    <span class="hero-sweep"></span>
    <span v-for="(spark, index) in sparks" :key="index" class="hero-spark"
      :style="{ left: spark.left, width: spark.size, animationDelay: spark.delay, animationDuration: spark.duration }"></span>
  </div>
</template>

<style scoped>
.hero-art {
  --ink: #9db9e3;
  --grid-step: 33px;
  position: absolute; inset: 0 0 0 37%; overflow: hidden; pointer-events: none;
  background: radial-gradient(ellipse at 72% 50%, color-mix(in srgb, var(--ink) 17%, transparent), transparent 68%);
  mask-image: linear-gradient(90deg, transparent, #000 34%);
}
:root[data-theme='light'] .hero-art { --ink: #466b98; }

/* 网格比容器宽一个步长，平移一个步长后与起点重合，循环无缝。 */
.hero-grid {
  position: absolute; inset: 0 auto 0 calc(var(--grid-step) * -1); width: calc(100% + var(--grid-step) * 2);
  background:
    repeating-linear-gradient(0deg, transparent 0 32px, color-mix(in srgb, var(--ink) 8%, transparent) 32px 33px),
    repeating-linear-gradient(90deg, transparent 0 32px, color-mix(in srgb, var(--ink) 5%, transparent) 32px 33px);
}

.hero-panels { position: absolute; inset-block: 0; right: 9%; width: min(80%, 24rem); }
.hero-panel {
  position: absolute; inset-block: -17%; width: 42%; transform: skewX(-26deg);
  border-inline: 1px solid color-mix(in srgb, var(--ink) 29%, transparent);
  background: linear-gradient(155deg, color-mix(in srgb, var(--ink) 23%, transparent), transparent 74%);
}
.hero-panel--back { right: 4%; }
.hero-panel--middle { right: 29%; }
.hero-panel--front {
  right: 54%;
  background: linear-gradient(155deg, transparent 32%, color-mix(in srgb, var(--ink) 14%, transparent));
}

/* 扫描光：一条斜向亮带从左扫到右，大部分时间停在视野外。 */
.hero-sweep {
  position: absolute; inset-block: -20%; left: 0; width: 22%; opacity: 0;
  transform: translateX(-120%) skewX(-26deg);
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--accent) 14%, transparent) 45%,
    color-mix(in srgb, #fff 10%, transparent) 50%, color-mix(in srgb, var(--accent) 14%, transparent) 55%, transparent);
}

.hero-spark {
  position: absolute; bottom: -6px; aspect-ratio: 1; opacity: 0;
  background: var(--accent); box-shadow: 0 0 6px color-mix(in srgb, var(--accent) 70%, transparent);
}

.hero-mark {
  position: absolute; top: 50%; left: 51%; width: clamp(2.4rem, 5.3vw, 4rem); aspect-ratio: 1;
  translate: -50% -50%;
}
.hero-core, .hero-ping {
  position: absolute; inset: 0; transform: rotate(45deg);
  border: 1px solid var(--accent);
}
.hero-core { background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 26%, transparent), transparent); }
.hero-core::after {
  content: ''; position: absolute; inset: 25%; border: inherit;
  background: color-mix(in srgb, var(--accent) 17%, transparent);
}
.hero-ping { opacity: 0; }

@media (max-width: 730px) {
  .hero-art { inset-inline-start: 43%; opacity: .66; }
  .hero-panels { right: 4%; width: 90%; }
}

@media (prefers-reduced-motion: no-preference) {
  .hero-grid { animation: hero-grid 9s linear infinite; }
  .hero-panel { animation: hero-enter .52s cubic-bezier(.2, .7, .2, 1) both, hero-drift 7s ease-in-out .6s infinite alternate; }
  .hero-panel--middle { animation-delay: .05s, 1.4s; animation-duration: .52s, 9s; }
  .hero-panel--front { animation-delay: .1s, .9s; animation-duration: .52s, 11s; }
  .hero-sweep { animation: hero-sweep 7.5s cubic-bezier(.45, 0, .2, 1) 1.2s infinite; }
  .hero-spark { animation-name: hero-spark; animation-timing-function: linear; animation-iteration-count: infinite; }
  .hero-core { animation: hero-enter-mark .45s .16s ease-out both, hero-breathe 3.6s ease-in-out .7s infinite; }
  .hero-ping { animation: hero-ping 3.6s cubic-bezier(.2, .6, .3, 1) .7s infinite; }
  .hero-ping--late { animation-delay: 2.5s; }
}

@keyframes hero-grid { to { transform: translateX(var(--grid-step)); } }
@keyframes hero-enter { from { opacity: 0; translate: 12px 0; } to { opacity: 1; translate: 0 0; } }
@keyframes hero-enter-mark { from { opacity: 0; scale: .8; } to { opacity: 1; scale: 1; } }
@keyframes hero-drift { from { translate: 0 0; } to { translate: -14px 0; } }
@keyframes hero-sweep {
  0% { opacity: 0; transform: translateX(-120%) skewX(-26deg); }
  8% { opacity: 1; }
  45% { opacity: 1; }
  55%, 100% { opacity: 0; transform: translateX(520%) skewX(-26deg); }
}
@keyframes hero-spark {
  0% { opacity: 0; transform: translateY(0) rotate(45deg); }
  15% { opacity: .75; }
  70% { opacity: .35; }
  100% { opacity: 0; transform: translateY(-190px) rotate(45deg); }
}
@keyframes hero-breathe {
  0%, 100% { box-shadow: 0 0 0 0 transparent; }
  50% { box-shadow: 0 0 18px 2px color-mix(in srgb, var(--accent) 35%, transparent); }
}
@keyframes hero-ping {
  0% { opacity: .7; scale: 1; }
  100% { opacity: 0; scale: 2.6; }
}
</style>
