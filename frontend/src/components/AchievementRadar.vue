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
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

const ORDER = ['COIN', 'EQUIP', 'CHAR', 'BOND', 'DAMAGE', 'KILL']
const ordered = computed(() => {
  const byKey = new Map(props.items.map(item => [item.key, item]))
  return ORDER.flatMap(key => {
    const item = byKey.get(key)
    return item ? [item] : []
  })
})
const description = computed(() => ordered.value.map(item => `${item.name} ${item.score}`).join('，'))

function option(): echarts.ComposeOption<RadarSeriesOption | RadarComponentOption> {
  const styles = getComputedStyle(document.documentElement)
  const accent = styles.getPropertyValue('--accent').trim()
  const line = styles.getPropertyValue('--line').trim()
  const muted = styles.getPropertyValue('--muted').trim()
  const inset = styles.getPropertyValue('--inset').trim()
  const items = ordered.value
  const scores = new Map(items.map(item => [item.name, item.score]))
  return {
    animation: false,
    radar: {
      center: ['50%', '50%'],
      radius: '59%',
      splitNumber: 4,
      startAngle: 90,
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
  chart.setOption(option(), { notMerge: true })
}

onMounted(() => {
  render()
  if (!host.value) return
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(host.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})

watch([description, theme], render, { flush: 'post' })
</script>

<template>
  <div ref="host" class="radar-host" role="img" :aria-label="description"></div>
</template>

<style scoped>
.radar-host { align-self: center; width: 100%; height: clamp(15rem, 70vw, 24rem); }
</style>
