<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { logbook } from '../context'
import { bondIcon, iconVersion } from '../icons'
import type { Point, Scope } from '../models'

echarts.use([LineChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer])

export type Metric = 'layers' | 'peak' | 'coins' | 'average' | 'kills' | 'rounds'

const props = defineProps<{
  points: Point[]
  metric: Metric
  title: string
  scope: Scope
}>()

const { theme } = logbook()
const container = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

const valueOf = (point: Point) => {
  if (props.metric === 'peak') return point.peak?.layers ?? 0
  if (props.metric === 'average') return point.average_coins ?? 0
  return point[props.metric] ?? 0
}

const byMatch = () => props.scope !== 'day'

function css(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue('--' + name).trim()
}

function describe(index: number): string {
  const point = props.points[index]
  if (!point) return ''
  const head = byMatch() ? `第 ${index + 1} 局 · ` : ''
  const outcome = byMatch() ? (point.result === 'loss' ? ' · 负' : ' · 胜') : ''
  const names = props.metric === 'peak' && point.peak ? ' · ' + point.peak.names.join('、') : ''
  const unit = props.metric === 'peak' ? ' 层' : ''
  return `${head}${point.label}${outcome}${names} · ${valueOf(point).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}${unit}`
}

function buildOption() {
  const items = props.points
  const match = byMatch()
  const muted = css('muted')
  const grid = css('chart-grid')
  const line = css('chart-line')
  const text = css('text')
  const labelBg = css('chart-label')
  const title = props.title
  const description = items.length
    ? (match ? `按开局时间排列 · ${items.length} 局` : `按开局日期统计 · ${items.length} 天`)
    : '当前筛选无对局'

  const data = items.map((point) => ({
    value: valueOf(point),
    itemStyle: { color: point.result === 'loss' && match ? css('loss') : css('win') },
    symbol: point.result === 'loss' && match ? 'diamond' : 'circle',
    symbolSize: 6,
  }))

  return {
    animation: false,
    backgroundColor: 'transparent',
    grid: { left: 48, right: 16, top: props.metric === 'peak' ? 46 : 22, bottom: 26 },
    aria: {
      enabled: true,
      label: { description: `${title}。${items.map((_, index) => describe(index)).join('，') || '当前筛选无对局'}` },
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: css('panel'),
      borderColor: css('line'),
      textStyle: { color: text, fontSize: 12 },
      axisPointer: { type: 'line', lineStyle: { color: grid } },
      formatter: (params: unknown) => {
        const list = params as { dataIndex: number }[]
        const index = list?.[0]?.dataIndex ?? 0
        return describe(index)
      },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: items.map((point, index) => (match ? String(index + 1) : point.label.slice(5))),
      axisLine: { lineStyle: { color: grid } },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 11, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      min: 0,
      splitNumber: 4,
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: grid } },
    },
    series: [{
      type: 'line',
      smooth: false,
      showSymbol: true,
      symbolSize: 6,
      lineStyle: { color: line, width: 2 },
      emphasis: { scale: 1.4, focus: 'series' },
      data,
    }],
    __description: description,
  }
}

function render() {
  if (!container.value) return
  chart ??= echarts.init(container.value, undefined, { renderer: 'canvas' })
  chart.setOption(buildOption(), { notMerge: true })
  chart.resize()
}

onMounted(() => {
  void nextTick(render)
  if (container.value) observer = new ResizeObserver(() => chart?.resize())
  if (container.value) observer?.observe(container.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
watch([() => props.points, () => props.metric, () => props.title, () => props.scope, iconVersion, theme], () => {
  void nextTick(render)
}, { flush: 'post' })
</script>

<template>
  <article class="trend-panel">
    <h3>{{ title }}</h3>
    <div ref="container" class="trend-canvas" role="img" />
  </article>
</template>
