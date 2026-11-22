<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { logbook } from '../context'
import { shortTime } from '../format'
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
const formatValue = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })

function css(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue('--' + name).trim()
}

function describe(index: number): string {
  const point = props.points[index]
  if (!point) return ''
  const head = byMatch() ? `第 ${index + 1} 局` : point.label
  const when = byMatch() ? shortTime(point.label) : ''
  const outcome = point.result === 'loss' ? '负' : point.result === 'win' ? '胜' : ''
  const parts = [head, when, outcome].filter(Boolean)
  const unit = props.metric === 'peak' ? ' 层' : ''
  const names = props.metric === 'peak' && point.peak && point.peak.names.length
    ? `（${point.peak.names.join('、')}）`
    : ''
  return `${parts.join(' · ')} · ${formatValue(valueOf(point))}${unit}${names}`
}

function buildOption() {
  const items = props.points
  const match = byMatch()
  const muted = css('muted')
  const grid = css('chart-grid')
  const line = css('chart-line')
  const text = css('text')
  const win = css('win')
  const loss = css('loss')

  const data = items.map((point, index) => ({
    value: valueOf(point),
    itemStyle: { color: point.result === 'loss' && match ? loss : win },
    symbol: point.result === 'loss' && match ? 'diamond' : 'circle',
    symbolSize: 7,
    label: {
      show: true,
      position: index === 0 ? 'right' : index === items.length - 1 ? 'left' : 'top',
      distance: 8,
      color: text,
      fontSize: 10,
      formatter: () => formatValue(valueOf(point)),
    },
  }))

  return {
    animation: true,
    animationDuration: 260,
    animationEasing: 'cubicOut' as const,
    backgroundColor: 'transparent',
    grid: { left: 62, right: 22, top: 32, bottom: 28 },
    aria: {
      enabled: true,
      label: { description: `${props.title}。${items.map((_, index) => describe(index)).join('，') || '当前筛选无对局'}` },
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: css('panel'),
      borderColor: css('line'),
      textStyle: { color: text, fontSize: 12 },
      extraCssText: 'border-radius:3px;box-shadow:0 10px 28px #00000055;',
      axisPointer: { type: 'line', lineStyle: { color: grid } },
      formatter: (params: unknown) => {
        const list = params as { dataIndex: number }[]
        return describe(list?.[0]?.dataIndex ?? 0)
      },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: items.map((point, index) => (match ? String(index + 1) : shortTime(point.label).slice(0, 5))),
      axisLine: { lineStyle: { color: grid } },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 10, hideOverlap: true, margin: 10 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      splitNumber: 3,
      max: (value: { max: number }) => Math.ceil(value.max * 1.15),
      axisLabel: {
        color: muted,
        fontSize: 10,
        margin: 8,
        formatter: (value: number) => value >= 1000
          ? `${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`
          : String(Math.round(value)),
      },
      splitLine: { lineStyle: { color: grid } },
    },
    series: [{
      type: 'line',
      smooth: false,
      showSymbol: true,
      symbolSize: 7,
      lineStyle: { color: line, width: 2 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: line + '33' },
          { offset: 1, color: line + '00' },
        ]),
      },
      emphasis: { scale: 1.5, focus: 'series' },
      data,
    }],
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
