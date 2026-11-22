<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CategoryScale, Chart, LineController, LineElement, LinearScale, PointElement, Tooltip } from 'chart.js'
import { dateTime } from '../format'
import type { Point, Scope } from '../models'

Chart.register(CategoryScale, LineController, LineElement, LinearScale, PointElement, Tooltip)

type Metric = 'layers' | 'peak' | 'coins' | 'average_coins' | 'kills' | 'rounds'
const props = defineProps<{ points: Point[]; metric: Metric; title: string; scope: Scope }>()
const canvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart | undefined

function render() {
  chart?.destroy()
  if (!canvas.value) return
  const colors = getComputedStyle(document.documentElement)
  const css = (name: string) => colors.getPropertyValue('--' + name).trim()
  const points = props.points
  chart = new Chart(canvas.value, {
    type: 'line',
    data: {
      labels: points.map((point, index) => props.scope === 'day' ? point.label.slice(5) : String(index + 1)),
      datasets: [{
        label: props.title,
        data: points.map(point => props.metric === 'peak' ? point.peak?.layers ?? null : point[props.metric] ?? null),
        borderColor: css('chart-line'),
        pointBackgroundColor: points.map(point => css(point.result === 'loss' ? 'loss' : 'win')),
        pointStyle: points.map(point => point.result === 'loss' ? 'rectRot' : 'circle'),
        pointRadius: points.length > 30 ? 1.5 : 3,
        borderWidth: 2,
      }],
    },
    options: {
      animation: false,
      maintainAspectRatio: false,
      normalized: true,
      interaction: { intersect: false, mode: 'index' },
      scales: {
        x: { ticks: { color: css('muted'), maxRotation: 0, maxTicksLimit: 8 }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { color: css('muted'), maxTicksLimit: 6 }, grid: { color: css('chart-grid') } },
      },
      plugins: {
        tooltip: { callbacks: {
          title: items => {
            const point = points[items[0]?.dataIndex]
            return point ? (props.scope === 'day' ? point.label : dateTime(point.label)) : ''
          },
          afterLabel: item => props.metric === 'peak' ? points[item.dataIndex]?.peak?.names.join('、') : undefined,
        } },
      },
    },
  })
}

onMounted(render)
watch(() => [props.points, props.metric, props.scope], render, { flush: 'post' })
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <article class="trend-panel">
    <h3>{{ title }}</h3>
    <div class="chart-frame"><canvas ref="canvas" role="img" :aria-label="title + '趋势，' + points.length + (scope === 'day' ? '天' : '局')" /></div>
  </article>
</template>
