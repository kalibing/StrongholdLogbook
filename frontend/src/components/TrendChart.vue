<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { bondIcon, iconVersion } from '../icons'
import type { Point, Scope } from '../models'

export type Metric = 'layers' | 'peak' | 'coins' | 'average' | 'kills' | 'rounds'

const props = defineProps<{
  points: Point[]
  metric: Metric
  title: string
  scope: Scope
}>()

const canvas = ref<HTMLCanvasElement | null>(null)
const note = ref('')
const description = ref('')

interface Series {
  label: string
  value: number
  won: boolean
  names: string
}

const series = computed<Series[]>(() => props.points.map(point => {
  const value = props.metric === 'peak'
    ? point.peak?.layers ?? 0
    : props.metric === 'average'
      ? point.average_coins ?? 0
      : point[props.metric] ?? 0
  return {
    label: point.label,
    value,
    won: point.result !== 'loss',
    names: point.peak?.names.join('、') ?? '',
  }
}))

const byMatch = computed(() => props.scope !== 'day')

const format = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
const describe = (item: Series, index: number) => {
  const head = byMatch.value ? `第 ${index + 1} 局 · ` : ''
  const outcome = byMatch.value ? (item.won ? ' · 胜' : ' · 负') : ''
  const names = props.metric === 'peak' && item.names ? ' · ' + item.names : ''
  const unit = props.metric === 'peak' ? ' 层' : ''
  return head + item.label + outcome + names + ' · ' + format(item.value) + unit
}

let observer: ResizeObserver | null = null
let hoverIndex = -1

function draw() {
  const element = canvas.value
  if (!element) return
  const width = element.clientWidth
  const height = element.clientHeight
  const context = element.getContext('2d')
  if (!context || width < 100) return

  const scale = window.devicePixelRatio || 1
  element.width = width * scale
  element.height = height * scale
  context.setTransform(scale, 0, 0, scale, 0, 0)
  context.clearRect(0, 0, width, height)

  const colors = getComputedStyle(document.documentElement)
  const color = (name: string) => colors.getPropertyValue('--' + name).trim()

  const items = series.value
  description.value = items.length
    ? (byMatch.value ? '按开局时间排列 · ' + items.length + ' 局' : '按开局日期统计 · ' + items.length + ' 天')
    : '当前筛选无对局'
  note.value = hoverIndex >= 0 && items[hoverIndex] ? describe(items[hoverIndex], hoverIndex) : description.value

  element.setAttribute('aria-label', props.title + '。' + items.map(describe).join('，'))
  if (!items.length) return

  const left = 49
  const right = width - 14
  const top = props.metric === 'peak' ? 44 : 12
  const bottom = height - 30
  const peak = Math.max(1, ...items.map(item => item.value))
  const step = Math.pow(10, Math.floor(Math.log10(peak / 4) || 0))
  const max = Math.ceil(peak / (4 * step)) * 4 * step

  context.font = '12px sans-serif'
  context.textAlign = 'left'
  for (let index = 0; index <= 4; index++) {
    const y = bottom - (bottom - top) * index / 4
    context.strokeStyle = color('chart-grid')
    context.beginPath()
    context.moveTo(left, y)
    context.lineTo(right, y)
    context.stroke()
    context.fillStyle = color('muted')
    context.fillText(format(max * index / 4), 0, y + 4)
  }

  const coords = items.map((item, index) => [
    items.length === 1 ? (left + right) / 2 : left + (right - left) * index / (items.length - 1),
    bottom - (bottom - top) * item.value / max,
  ] as [number, number])

  context.strokeStyle = color('chart-line')
  context.lineWidth = 2
  context.beginPath()
  coords.forEach(([x, y], index) => index ? context.lineTo(x, y) : context.moveTo(x, y))
  context.stroke()

  coords.forEach(([x, y], index) => {
    const won = items[index].won
    context.fillStyle = color(!byMatch.value || won ? 'win' : 'loss')
    context.beginPath()
    if (byMatch.value && !won) {
      context.moveTo(x, y - 4)
      context.lineTo(x + 4, y)
      context.lineTo(x, y + 4)
      context.lineTo(x - 4, y)
      context.closePath()
    } else {
      context.arc(x, y, 3, 0, Math.PI * 2)
    }
    context.fill()
  })

  context.fillStyle = color('muted')
  context.textAlign = 'center'
  const stride = Math.max(1, Math.ceil(items.length / Math.max(2, Math.floor((right - left) / 62))))
  items.forEach((item, index) => {
    if (index % stride === 0 && (index === 0 || index < items.length - stride) || index === items.length - 1) {
      context.fillText(byMatch.value ? String(index + 1) : item.label.slice(5), Math.min(width - 18, coords[index][0]), height - 6)
    }
  })

  const occupied: { x: number, y: number, w: number, h: number }[] = []
  const labelStep = Math.max(1, Math.ceil(items.length / 10))
  const lineHeight = 14
  for (let index = 0; index < items.length; index += labelStep) {
    const item = items[index]
    const first = item.names.split('、')[0]
    const name = props.metric === 'peak' ? first + (item.names.includes('、') ? '等' : '') : ''
    const icon = name ? bondIcon(first) : null
    const hasIcon = Boolean(icon && icon.complete && icon.naturalWidth)
    const layer = format(item.value) + (name ? ' 层' : '')
    const labelWidth = Math.max(context.measureText(name).width + (hasIcon ? 17 : 0), context.measureText(layer).width) + 10
    const [x, y] = coords[index]
    const lastLabelX = Math.max(0, width - labelWidth)
    const leftEdge = Math.min(lastLabelX, Math.max(left, x - labelWidth / 2))
    const labelHeight = lineHeight * (name ? 2 : 1) + 4
    const candidates = [y - labelHeight - 8, y + 8, y - labelHeight - 32, y + 32]
    const labelY = candidates.find(candidate => candidate >= 0 && candidate + labelHeight < height - 22
      && occupied.every(rect => leftEdge + labelWidth + 3 <= rect.x || rect.x + rect.w + 3 <= leftEdge
        || candidate + labelHeight + 2 <= rect.y || rect.y + rect.h + 2 <= candidate))
    if (labelY === undefined) continue
    occupied.push({ x: leftEdge, y: labelY, w: labelWidth, h: labelHeight })

    context.beginPath()
    context.strokeStyle = color('control-line')
    context.lineWidth = 1
    context.moveTo(x, y)
    context.lineTo(leftEdge + labelWidth / 2, labelY < y ? labelY + labelHeight : labelY)
    context.stroke()

    context.fillStyle = color('chart-label')
    context.fillRect(leftEdge, labelY, labelWidth, labelHeight)
    context.fillStyle = color(!byMatch.value || item.won ? 'win' : 'loss')
    if (name) {
      if (hasIcon && icon) context.drawImage(icon, leftEdge + 4, labelY + 2, 13, 13)
      context.textAlign = 'center'
      context.fillText(name, leftEdge + labelWidth / 2 + (hasIcon ? 7 : 0), labelY + 13)
    }
    context.fillStyle = color('text')
    context.textAlign = 'center'
    context.fillText(layer, leftEdge + labelWidth / 2, labelY + (name ? 27 : 13))
  }
}

function onPointerMove(event: PointerEvent) {
  const element = canvas.value
  if (!element || !series.value.length) return
  const width = element.clientWidth
  const left = 49
  const right = width - 14
  const ratio = (event.offsetX - left) / (right - left)
  hoverIndex = Math.max(0, Math.min(series.value.length - 1, Math.round(ratio * (series.value.length - 1))))
  note.value = describe(series.value[hoverIndex], hoverIndex)
}

function onPointerLeave() {
  hoverIndex = -1
  note.value = description.value
}

function redraw() {
  void nextTick(draw)
}

onMounted(() => {
  redraw()
  if (canvas.value) observer = new ResizeObserver(redraw)
  if (canvas.value) observer?.observe(canvas.value)
})
onBeforeUnmount(() => observer?.disconnect())
watch([() => props.points, () => props.metric, () => props.title, () => props.scope, iconVersion], redraw, { flush: 'post' })
</script>

<template>
  <article class="trend-panel">
    <h3>{{ title }}</h3>
    <canvas ref="canvas" class="trend-canvas" role="img" @pointermove="onPointerMove" @pointerleave="onPointerLeave" />
    <p class="muted trend-note">{{ note }}</p>
  </article>
</template>
