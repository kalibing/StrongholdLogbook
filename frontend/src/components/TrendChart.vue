<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, type BarSeriesOption, type LineSeriesOption } from 'echarts/charts'
import { AriaComponent, GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { LabelLayout } from 'echarts/features'
import { CanvasRenderer } from 'echarts/renderers'
import { BOND_ICONS, BOND_METRIC_ICON, FUNDS_ICON, KILLS_ICON, ROUND_ICON } from '../assets'
import { logbook } from '../context'
import { number, pickMajorBond, shortTime } from '../format'
import type { Point } from '../models'

echarts.use([BarChart, LineChart, GridComponent, MarkLineComponent, TooltipComponent, AriaComponent, LabelLayout, CanvasRenderer])

export type Metric = 'layers' | 'peak' | 'coins' | 'kills' | 'rounds'
const units: Record<Metric, string> = {
  layers: '层', peak: '层', coins: '金币', kills: '次', rounds: '回合',
}
const metricArt: Record<Metric, string> = {
  layers: BOND_METRIC_ICON, peak: BOND_METRIC_ICON, coins: FUNDS_ICON,
  kills: KILLS_ICON, rounds: ROUND_ICON,
}

const props = defineProps<{
  points: Point[]
  metric: Metric
  title: string
  /** 按日聚合的点：没有单局胜负，标签是日期。 */
  daily?: boolean
}>()
const emit = defineEmits<{ openMatch: [id: string] }>()

const { theme } = logbook()
const container = ref<HTMLDivElement | null>(null)
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
const reduceMotion = ref(motionPreference.matches)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

const valueOf = (point: Point) => {
  if (props.metric === 'peak') return point.peak?.layers ?? null
  return point[props.metric] ?? null
}
const hasValues = computed(() => props.points.some(point => valueOf(point) !== null))
const peakAverage = computed(() => {
  if (props.metric !== 'peak') return null
  const peaks = props.points.flatMap(point => point.peak ? [point.peak.layers] : [])
  return peaks.length ? peaks.reduce((sum, value) => sum + value, 0) / peaks.length : null
})
const averageText = computed(() => peakAverage.value === null ? '' : `单项最高场均 ${number(peakAverage.value)} 层`)

function css(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue('--' + name).trim()
}

function describe(index: number) {
  const point = props.points[index]
  const heading = props.daily
    ? `${point.label} · ${point.wins ?? 0} 胜 ${point.losses ?? 0} 负`
    : `第 ${index + 1} 局 · ${shortTime(point.label)}`
  const outcome = point.result === 'loss' ? '负' : point.result === 'win' ? '胜' : ''
  const names = props.metric === 'peak' && point.peak && point.peak.names.length
    ? point.peak.names.join('、')
    : ''
  const value = valueOf(point)
  return { heading, outcome, names, valueText: value === null ? '无记录' : `${number(value)} ${units[props.metric]}` }
}

function buildOption() {
  const items = props.points
  const muted = css('muted')
  const grid = css('chart-grid')
  const text = css('text')
  const win = css('win')
  const loss = css('loss')
  const averageColor = css('chart-average')
  const panel = css('panel')
  const neutral = css('chart-line')
  const accent = css('accent')
  // 数字用站点的窄体数字字体，中文字符在 canvas 里按字体列表逐字回落到正文字体。
  const fontFamily = `${css('numbers')}, ${getComputedStyle(document.documentElement).fontFamily}`
  const fade = (color: string, from: number, to: number) => new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: color + Math.round(from * 255).toString(16).padStart(2, '0') },
    { offset: 1, color: color + Math.round(to * 255).toString(16).padStart(2, '0') },
  ])
  const peak = props.metric === 'peak'
  const colorOf = (point: Point) => props.daily ? neutral : point.result === 'loss' ? loss : win
  const axisLabel = (index: number) => props.daily ? items[index].label.slice(5) : String(index + 1)

  const showLabels = items.length <= 10
  const peakBonds = peak
    ? items.map(point => pickMajorBond(point.peak?.names ?? []))
    : []
  const hasBondLabels = peakBonds.some(Boolean)
  const iconBonds = [...new Set(peakBonds.filter(name => Boolean(BOND_ICONS[name])))]
  const iconKeys = new Map(iconBonds.map((name, index) => [name, `bond${index}`]))
  const axisIcons = Object.fromEntries(iconBonds.map(name => [
    iconKeys.get(name)!,
    {
      width: 25, height: 25, lineHeight: 30,
      backgroundColor: { image: theme.value === 'light' ? BOND_ICONS[name].replace('/art/', '/art/bond-light/') : BOND_ICONS[name] },
    },
  ]))
  const label = {
    show: showLabels,
    position: 'top' as const,
    distance: 6,
    color: text,
    fontFamily,
    fontSize: 13,
    fontWeight: 700,
    formatter: ({ dataIndex }: { dataIndex: number }) => {
      const value = valueOf(items[dataIndex])
      return value === null ? '' : number(value)
    },
  }
  const series: BarSeriesOption | LineSeriesOption = peak ? {
    type: 'line',
    connectNulls: false,
    symbol: 'diamond',
    symbolSize: showLabels ? 11 : 7,
    lineStyle: { color: accent, width: 2 },
    areaStyle: { color: fade(accent, .22, 0) },
    emphasis: { scale: 1.4 },
    label: { ...label, distance: 8 },
    labelLayout: { hideOverlap: true },
    markLine: peakAverage.value === null ? undefined : {
      silent: true,
      symbol: 'none',
      label: { show: false },
      lineStyle: { color: averageColor, width: 1, type: [5, 4] },
      data: [{ yAxis: peakAverage.value }],
    },
    data: items.map(point => ({
      value: valueOf(point),
      itemStyle: { color: colorOf(point), borderColor: panel, borderWidth: 2 },
    })),
  } : {
    type: 'bar',
    barMaxWidth: 28,
    label,
    labelLayout: { hideOverlap: true },
    data: items.map(point => {
      const value = valueOf(point)
      const color = colorOf(point)
      // 方角柱：顶部实色、向下渐隐，顶边一道实线像刻度读数。
      return { value, itemStyle: { color: fade(color, .75, .18), borderColor: color, borderWidth: 0, borderRadius: 0, shadowColor: color, shadowOffsetY: -2 } }
    }),
  }

  return {
    animation: !reduceMotion.value,
    animationDuration: 160,
    animationDurationUpdate: 0,
    animationEasing: 'cubicOut' as const,
    backgroundColor: 'transparent',
    textStyle: { fontFamily },
    grid: { left: 38, right: 12, top: 24, bottom: (showLabels && !props.daily ? 43 : 28) + (hasBondLabels ? 59 : 0) },
    aria: {
      enabled: true,
      label: {
        description: `${props.title}。${items.map((_, index) => {
          const { heading, outcome, valueText, names } = describe(index)
          return [heading, outcome, valueText, names].filter(Boolean).join(' · ')
        }).join('，') || '当前筛选无对局'}${averageText.value ? `。${averageText.value}` : ''}`,
      },
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      renderMode: 'html',
      className: 'trend-tooltip',
      backgroundColor: 'transparent',
      borderWidth: 0,
      padding: 0,
      textStyle: { color: text, fontSize: 12 },
      axisPointer: peak
        ? { type: 'line', lineStyle: { color: accent, width: 1, type: [3, 3] } }
        : { type: 'shadow', shadowStyle: { color: accent + '14' } },
      formatter: (params: unknown) => {
        const list = params as { dataIndex: number }[]
        const index = list?.[0]?.dataIndex
        if (index === undefined || !items[index]) return ''
        const { heading, outcome, valueText, names } = describe(index)
        const outcomeText = outcome
          ? `<strong class="${outcome === '胜' ? 'win-key' : 'loss-key'}">${outcome}</strong>`
          : ''
        return [
          `<div>${echarts.format.encodeHTML(heading)}</div>`,
          outcomeText && `<div>${outcomeText}</div>`,
          `<strong class="trend-tooltip-value">${valueText}</strong>`,
          names && `<div>${echarts.format.encodeHTML(names)}</div>`,
          averageText.value && `<div class="trend-tooltip-average">${averageText.value}</div>`,
          items[index].match_id && '<div class="trend-tooltip-hint">点击查看单局战报</div>',
        ].filter(Boolean).join('')
      },
    },
    xAxis: {
      type: 'category',
      boundaryGap: true,
      data: items.map((_, index) => axisLabel(index)),
      axisLine: { lineStyle: { color: grid } },
      axisTick: { show: false },
      axisLabel: {
        color: muted,
        fontFamily,
        fontSize: 12,
        margin: 10,
        interval: showLabels ? 0 : 'auto' as const,
        hideOverlap: !showLabels,
        formatter: (value: string, index: number) => {
          const result = showLabels && !props.daily
            ? (items[index].result === 'loss' ? '\n{loss|负}' : '\n{win|胜}')
            : ''
          const name = peakBonds[index]
          if (!name) return value + result
          const icon = iconKeys.get(name)
          const characters = [...name]
          const compact = (container.value?.clientWidth ?? 0) < 520
          const rows = compact && characters.length > 2
            ? [characters.slice(0, 2).join(''), characters.length > 4 ? characters[2] + '…' : characters.slice(2).join('')]
            : [characters.length > 8 ? characters.slice(0, 7).join('') + '…' : name]
          const bondLabel = rows.map(row => `{bondName|${row.replace(/[{}|\r\n]/g, '')}}`).join('\n')
          return `${value}${result}${icon ? `\n{${icon}| }` : ''}\n${bondLabel}`
        },
        rich: {
          win: { color: win, lineHeight: 16 }, loss: { color: loss, lineHeight: 16 },
          bondName: { color: text, fontSize: 11, lineHeight: 14 },
          ...axisIcons,
        },
      },
    },
    yAxis: {
      type: 'value',
      min: 0,
      splitNumber: 4,
      minInterval: 1,
      axisLabel: {
        color: muted,
        fontFamily,
        fontSize: 11,
        margin: 10,
        formatter: (value: number) => value >= 1000
          ? `${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`
          : number(value),
      },
      splitLine: { lineStyle: { color: grid, type: [4, 4] } },
    },
    series: [series],
  }
}

function render() {
  if (!container.value) return
  chart ??= echarts.init(container.value, undefined, { renderer: 'canvas' })
  chart.setOption(buildOption(), { notMerge: true })
}

function updateMotion() {
  reduceMotion.value = motionPreference.matches
}

function matchAt(x: number, y: number) {
  if (!chart?.containPixel({ gridIndex: 0 }, [x, y])) return null
  const index = chart.convertFromPixel({ xAxisIndex: 0 }, x)
  return props.points[index]?.match_id ?? null
}

onMounted(() => {
  motionPreference.addEventListener('change', updateMotion)
  render()
  if (!container.value) return
  const surface = chart?.getZr()
  surface?.on('mousemove', event => surface.setCursorStyle(matchAt(event.offsetX, event.offsetY) ? 'pointer' : 'default'))
  surface?.on('click', event => {
    const id = matchAt(event.offsetX, event.offsetY)
    if (!id) return
    chart?.dispatchAction({ type: 'hideTip' })
    emit('openMatch', id)
  })
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(container.value)
})
onBeforeUnmount(() => {
  motionPreference.removeEventListener('change', updateMotion)
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
watch([() => props.points, () => props.metric, () => props.title, () => props.daily, theme, reduceMotion], render, { flush: 'post' })
</script>

<template>
  <article class="trend-panel" :class="{ 'trend-panel--peak': metric === 'peak' }">
    <div class="trend-heading">
      <h3 class="trend-metric">
        <img class="trend-art" :class="{ 'trend-art--bond': metric === 'peak' || metric === 'layers' }"
          :src="metricArt[metric]" width="22" height="20" alt="">
        <span>{{ title }}</span>
      </h3>
      <span v-if="averageText" class="trend-average-key" title="当前图表内有记录的各局单项最高层数取平均">{{ averageText }}</span>
    </div>
    <div class="chart-body">
      <div ref="container" class="trend-canvas" :class="{ 'chart-hidden': !hasValues }" :aria-hidden="!hasValues" role="img" />
      <p v-if="!hasValues" class="chart-empty muted">暂无记录</p>
    </div>
  </article>
</template>

<style scoped>
.trend-heading { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: .45rem .75rem; }
.trend-metric { display: flex; align-items: center; gap: .45rem; }
.trend-art { flex: none; object-fit: contain; }
.trend-average-key { display: inline-flex; align-items: center; gap: .4rem; color: var(--chart-average); font-size: .8rem; }
.trend-average-key::before { content: ''; width: 1.35rem; border-top: 2px dashed currentColor; }
.trend-panel--peak { grid-column: 1 / -1; }
.trend-panel--peak .trend-canvas { height: 285px; }
.chart-body { position: relative; min-width: 0; }
.chart-hidden { visibility: hidden; }
.chart-empty { position: absolute; inset: 0; display: grid; place-items: center; }
:deep(.trend-tooltip-value) { font-family: var(--numbers); font-size: 1rem; }
:deep(.trend-tooltip-average) { color: var(--chart-average); }
:deep(.trend-tooltip-hint) { color: var(--muted); font-size: .72rem; margin-top: .2rem; }
</style>
