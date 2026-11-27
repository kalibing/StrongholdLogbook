<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { RadarChart, type RadarSeriesOption } from 'echarts/charts'
import { RadarComponent, type RadarComponentOption } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { logbook } from '../context'

echarts.use([RadarChart, RadarComponent, CanvasRenderer])

interface Item {
  key: string
  name: string
  score: number
}

const props = defineProps<{ items: Item[] }>()
const { theme } = logbook()
const host = ref<HTMLDivElement | null>(null)
const hover = ref<{ index: number; x: number; y: number; pointX: number; pointY: number } | null>(null)
const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

const ORDER = ['COIN', 'EQUIP', 'CHAR', 'BOND', 'DAMAGE', 'KILL']
const RADIUS = 59
const START_ANGLE = 90
const ordered = computed(() => {
  const byKey = new Map(props.items.map(item => [item.key, item]))
  return ORDER.flatMap(key => {
    const item = byKey.get(key)
    return item ? [item] : []
  })
})
const description = computed(() => ordered.value.map(item => `${item.name} ${item.score}`).join('，'))
const hoveredItem = computed(() => hover.value ? ordered.value[hover.value.index] : undefined)

function findNearest(event: PointerEvent) {
  const bounds = host.value?.getBoundingClientRect()
  if (!bounds || !ordered.value.length) return
  const x = event.clientX - bounds.left
  const y = event.clientY - bounds.top
  const dx = x - bounds.width / 2
  const dy = y - bounds.height / 2
  const radius = Math.min(bounds.width, bounds.height) * RADIUS / 200
  const distance = Math.hypot(dx, dy)
  if (distance > radius + 44) {
    hover.value = null
    return
  }

  let closest = Infinity
  let index = 0
  let pointX = 0
  let pointY = 0
  ordered.value.forEach((item, i, items) => {
    const angle = START_ANGLE * Math.PI / 180 + i * Math.PI * 2 / items.length
    // Outside the plot, match the axis labels instead of pulling toward higher scores.
    const length = distance > radius ? radius : radius * item.score / 100
    const axisX = Math.cos(angle)
    const axisY = -Math.sin(angle)
    const squaredDistance = (dx - length * axisX) ** 2 + (dy - length * axisY) ** 2
    if (squaredDistance < closest) {
      closest = squaredDistance
      index = i
      pointX = bounds.width / 2 + radius * item.score / 100 * axisX
      pointY = bounds.height / 2 + radius * item.score / 100 * axisY
    }
  })
  hover.value = { index, pointX, pointY, x: Math.max(70, Math.min(bounds.width - 70, x)), y: Math.max(44, y) }
}

function option(): echarts.ComposeOption<RadarSeriesOption | RadarComponentOption> {
  const styles = getComputedStyle(document.documentElement)
  const accent = styles.getPropertyValue('--accent').trim()
  const line = styles.getPropertyValue('--line').trim()
  const muted = styles.getPropertyValue('--muted').trim()
  const inset = styles.getPropertyValue('--inset').trim()
  const items = ordered.value
  const scores = new Map(items.map(item => [item.name, item.score]))
  return {
    animation: !motion.matches,
    animationDuration: 620,
    animationDurationUpdate: 420,
    animationEasing: 'cubicOut',
    radar: {
      center: ['50%', '50%'],
      radius: `${RADIUS}%`,
      splitNumber: 4,
      startAngle: START_ANGLE,
      indicator: items.map(item => ({ name: item.name, min: 0, max: 100 })),
      axisNameGap: 8,
      axisName: {
        formatter: name => name ? `{score|${scores.get(name)}}\n{name|${name}}` : '',
        rich: {
          score: { color: accent, fontSize: 18, fontWeight: 'bold', lineHeight: 22, align: 'center' },
          name: { color: muted, fontSize: 12, lineHeight: 18, align: 'center' },
        },
      },
      axisLine: { lineStyle: { color: line } },
      splitLine: { lineStyle: { color: line } },
      splitArea: { areaStyle: { color: ['transparent', inset] } },
    },
    series: [
      {
        type: 'radar',
        silent: true,
        symbolSize: 6,
        lineStyle: { color: accent, width: 2 },
        itemStyle: { color: accent },
        areaStyle: { color: accent, opacity: 0.21 },
        data: [{ value: items.map(item => item.score), name: '六维成就' }],
      },
    ],
  }
}

function render() {
  if (!host.value) return
  if (!chart) chart = echarts.init(host.value, undefined, { renderer: 'canvas' })
  chart.setOption(option())
}

onMounted(() => {
  motion.addEventListener('change', render)
  render()
  if (!host.value) return
  observer = new ResizeObserver(() => {
    if (!chart || !host.value || (chart.getWidth() === host.value.clientWidth && chart.getHeight() === host.value.clientHeight)) return
    hover.value = null
    chart.resize()
  })
  observer.observe(host.value)
})

onBeforeUnmount(() => {
  motion.removeEventListener('change', render)
  observer?.disconnect()
  chart?.dispose()
  chart = null
})

watch([description, theme], render, { flush: 'post' })
</script>

<template>
  <div class="radar-frame" @pointermove="findNearest" @pointerleave="hover = null">
    <div ref="host" class="radar-host" role="img" :aria-label="description"></div>
    <span v-if="hover && hoveredItem" :key="hoveredItem.key" class="radar-focus" aria-hidden="true"
      :style="{ left: `${hover.pointX}px`, top: `${hover.pointY}px` }"></span>
    <Transition name="radar-tip">
      <div v-if="hover && hoveredItem" class="radar-tooltip" role="tooltip"
        :style="{ left: `${hover.x}px`, top: `${hover.y}px` }">
        {{ hoveredItem.name }} <strong>{{ hoveredItem.score }}</strong><span class="muted"> / 100</span>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.radar-frame { position: relative; align-self: center; min-width: 0; }
.radar-host { width: 100%; height: clamp(15rem, 70vw, 24rem); }
.radar-tooltip {
  position: absolute; z-index: 1; pointer-events: none; transform: translate(-50%, calc(-100% - 8px));
  padding: .32rem .55rem; border: 1px solid var(--control-line); border-radius: var(--radius);
  background: var(--panel); color: var(--text); box-shadow: 0 4px 14px #0003;
  font-size: .875rem; white-space: nowrap;
}
.radar-tooltip strong { margin-left: .25rem; color: var(--accent); font-family: var(--numbers); }
.radar-focus {
  position: absolute; width: 12px; aspect-ratio: 1; pointer-events: none; translate: -50% -50%;
  border-radius: 50%; border: 2px solid var(--accent);
  background: var(--panel); box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 24%, transparent);
}
@media (prefers-reduced-motion: no-preference) {
  .radar-focus { animation: radar-focus-in .22s ease-out; }
  .radar-tip-enter-active, .radar-tip-leave-active { transition: opacity .14s ease, transform .14s ease; }
  .radar-tip-enter-from, .radar-tip-leave-to { opacity: 0; transform: translate(-50%, calc(-100% - 3px)); }
}
@keyframes radar-focus-in { from { scale: .55; opacity: .55; } to { scale: 1; opacity: 1; } }
</style>
