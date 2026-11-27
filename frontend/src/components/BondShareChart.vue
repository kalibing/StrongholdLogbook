<script setup lang="ts">
import { TransitionGroup, computed, ref, useId, watch } from 'vue'
import { NIcon, NSwitch } from 'naive-ui'
import { ChevronDown } from '@vicons/ionicons5'
import * as echarts from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { BOND_ICONS } from '../assets'
import { logbook } from '../context'
import { number, percent } from '../format'
import type { BondLayers } from '../models'

echarts.use([PieChart, CanvasRenderer])

const props = defineProps<{ bonds: BondLayers[]; description: string }>()
const titleId = useId()
const { theme } = logbook()
const container = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
const colors = ['#628ef5', '#36bda3', '#a486ef', '#f5b552', '#45a9d1', '#eb7f9c', '#8593ae']
// 展开「其他」后的配色：比前 6 种降一档饱和度的另一组色相，彼此能区分，又不会抢前 6 种的视觉重心。
const foldedColors = ['#9fb86a', '#c98b5e', '#8a8fd6', '#5fa3a8', '#c27aa8', '#d2b061', '#6f9fd0', '#c97a7a', '#7cbf8e', '#a98fcf']
const MAJOR = 6
const EXPANDED_KEY = 'logbook:bond-share-expanded'

type Slice = BondLayers & { share: number; color: string; others?: boolean; folded?: boolean }

function readExpanded() {
  try { return localStorage.getItem(EXPANDED_KEY) === '1' } catch { return false }
}
const expanded = ref(readExpanded())
watch(expanded, value => {
  try { localStorage.setItem(EXPANDED_KEY, value ? '1' : '0') } catch { /* 隐私模式等无存储时忽略 */ }
  selectedIndex.value = null
  previewIndex.value = null
  previewOthers.value = false
})

const previewIndex = ref<number | null>(null)
const previewOthers = ref(false)
const selectedIndex = ref<number | null>(null)
const total = computed(() => props.bonds.reduce((sum, bond) => sum + bond.layers, 0))
// 只剩一种时直接列出来，折成「其他 1 种」没有意义。
const folded = computed(() => props.bonds.length > MAJOR + 1 ? props.bonds.slice(MAJOR) : [])
const shown = computed(() => folded.value.length ? props.bonds.slice(0, MAJOR) : props.bonds)
const othersSlice = computed<Slice>(() => {
  const layers = folded.value.reduce((sum, bond) => sum + bond.layers, 0)
  return { name: `其他 ${folded.value.length} 种`, layers, share: layers / total.value, color: colors[MAJOR], others: true }
})
const slices = computed<Slice[]>(() => {
  const list: Slice[] = shown.value.map((bond, index) => ({ ...bond, share: bond.layers / total.value, color: colors[index] }))
  if (!folded.value.length) return list
  if (!expanded.value) return [...list, othersSlice.value]
  return [...list, ...folded.value.map((bond, index) => ({
    ...bond, share: bond.layers / total.value, color: foldedColors[index % foldedColors.length], folded: true,
  }))]
})
const foldedIndices = computed(() => slices.value.flatMap((slice, index) => slice.folded ? [index] : []))

/** 图例行：展开时在被折叠的盟约前插一行「其他 N 种」小计，点它收起。 */
type Row = { kind: 'slice'; slice: Slice; index: number } | { kind: 'group' }
const rows = computed<Row[]>(() => {
  const result: Row[] = []
  slices.value.forEach((slice, index) => {
    if (slice.folded && !slices.value[index - 1]?.folded) result.push({ kind: 'group' })
    result.push({ kind: 'slice', slice, index })
  })
  return result
})

const activeIndex = computed(() => previewIndex.value ?? selectedIndex.value)
const activeSlice = computed(() => previewOthers.value ? othersSlice.value
  : activeIndex.value === null ? null : slices.value[activeIndex.value])
const highlighted = computed(() => previewOthers.value ? foldedIndices.value
  : activeIndex.value === null ? [] : [activeIndex.value])
const shareText = (share: number) => share < .001 ? '<0.1%' : percent(share)

function drawChart() {
  const css = getComputedStyle(document.documentElement)
  const panel = css.getPropertyValue('--panel').trim()
  chart?.setOption({
    animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    // 展开 / 收起时沿用同一个系列，ECharts 按名字对齐扇区做角度过渡：
    // 「其他」那块灰色扇区原地裂成若干小扇区，而不是整圈重画一遍。
    animationDurationUpdate: 520,
    animationEasingUpdate: 'cubicInOut',
    // 不用浮动 tooltip：悬停时圆环中心已显示该盟约的层数与占比，浮层只会盖住中心和图例。
    series: [{
      id: 'share', type: 'pie', radius: ['68%', '88%'], startAngle: 90, label: { show: false },
      itemStyle: { borderColor: panel, borderWidth: 2, borderRadius: 4 },
      emphasis: { focus: 'self', scaleSize: 5 },
      stateAnimation: { duration: 200, easing: 'cubicOut' },
      blur: { itemStyle: { opacity: .32 } },
      data: slices.value.map(slice => ({
        name: slice.name, value: slice.layers,
        itemStyle: { color: slice.color, borderWidth: slice.folded ? 1 : 2 },
      })),
    }],
  })
}

function activate(index: number) {
  if (slices.value[index]?.others) {
    expanded.value = true
    return
  }
  selectedIndex.value = selectedIndex.value === index ? null : index
}

watch(container, (element, _, onCleanup) => {
  if (!element) return
  const instance = echarts.init(element)
  chart = instance
  instance.on('mouseover', 'series.pie', event => { previewIndex.value = event.dataIndex })
  instance.on('mouseout', 'series.pie', () => { previewIndex.value = null })
  instance.on('click', 'series.pie', event => { activate(event.dataIndex) })
  drawChart()
  const observer = new ResizeObserver(() => instance.resize())
  observer.observe(element)
  onCleanup(() => {
    observer.disconnect()
    instance.dispose()
    chart = null
  })
}, { flush: 'post' })
watch([slices, theme], drawChart, { flush: 'post' })
watch(() => props.bonds, () => {
  selectedIndex.value = null
  previewIndex.value = null
  previewOthers.value = false
})
watch(highlighted, (indices, previous) => {
  if (previous?.length) chart?.dispatchAction({ type: 'downplay', seriesIndex: 0, dataIndex: previous })
  if (indices.length) chart?.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: indices })
}, { flush: 'post' })
</script>

<template>
  <section class="panel bond-share" :aria-labelledby="titleId"
    @keydown.escape="selectedIndex = null; previewIndex = null; previewOthers = false">
    <header>
      <div>
        <h2 :id="titleId">盟约层数分布</h2>
        <p class="muted share-note">{{ description }}</p>
      </div>
      <label v-if="folded.length" class="share-toggle">
        <NSwitch v-model:value="expanded" size="small" />
        <span>展开其他</span>
      </label>
    </header>
    <div v-if="total" class="share-body">
      <div class="share-graphic">
        <div ref="container" class="share-pie" aria-hidden="true"></div>
        <div class="share-total">
          <b>{{ number(activeSlice?.layers ?? total) }}</b>
          <span>{{ activeSlice?.name ?? '累计层数' }}</span>
          <small v-if="activeSlice" class="share-active-percent" :style="{ '--slice-color': activeSlice.color }">{{ shareText(activeSlice.share) }}</small>
        </div>
      </div>
      <div class="share-key">
        <div class="share-key-head" aria-hidden="true"><span>盟约</span><span>层数</span><span>占比</span></div>
        <TransitionGroup tag="ul" name="share-item" class="share-legend" :class="{ 'share-legend--expanded': expanded && folded.length }">
          <li v-for="(row, position) in rows" :key="row.kind === 'group' ? '__group' : row.slice.name"
            :style="{ '--enter-delay': `${Math.max(0, position - MAJOR) * 22}ms` }">
            <button v-if="row.kind === 'group'" type="button" class="share-row share-row--group" :class="{ active: previewOthers }"
              aria-expanded="true" :aria-label="`收起${othersSlice.name}，共 ${number(othersSlice.layers)} 层，占 ${shareText(othersSlice.share)}`"
              @pointerenter="previewOthers = true" @pointerleave="previewOthers = false"
              @focus="previewOthers = true" @blur="previewOthers = false" @click="expanded = false">
              <span class="share-name">
                <i :style="{ background: othersSlice.color }" aria-hidden="true"></i>
                <span>{{ othersSlice.name }}<NIcon class="share-chevron share-chevron--open" :component="ChevronDown" :size="13" /></span>
              </span>
              <span class="share-layers">{{ number(othersSlice.layers) }}</span>
              <b class="share-percent">{{ shareText(othersSlice.share) }}</b>
            </button>
            <button v-else type="button" class="share-row"
              :class="{ active: highlighted.includes(row.index), 'share-row--sub': row.slice.folded }"
              :aria-pressed="row.slice.others ? undefined : selectedIndex === row.index"
              :aria-expanded="row.slice.others ? false : undefined"
              :aria-label="`${row.slice.others ? '展开' : ''}${row.slice.name}，${number(row.slice.layers)} 层，占 ${shareText(row.slice.share)}`"
              @pointerenter="previewIndex = row.index" @pointerleave="previewIndex = null"
              @focus="previewIndex = row.index" @blur="previewIndex = null" @click="activate(row.index)">
              <span class="share-name">
                <i :style="{ background: row.slice.color }" aria-hidden="true"></i>
                <img v-if="BOND_ICONS[row.slice.name]" :src="BOND_ICONS[row.slice.name]" width="16" height="16" alt="">
                <span>{{ row.slice.name }}<NIcon v-if="row.slice.others" class="share-chevron" :component="ChevronDown" :size="13" /></span>
              </span>
              <span class="share-layers">{{ number(row.slice.layers) }}</span>
              <b class="share-percent">{{ shareText(row.slice.share) }}</b>
            </button>
          </li>
        </TransitionGroup>
      </div>
    </div>
    <p v-else class="muted share-empty">暂无盟约层数记录。</p>
  </section>
</template>

<style scoped>
.bond-share { padding: 1.2rem clamp(1rem, 2.5vw, 1.65rem); container-type: inline-size; }
.bond-share header { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: .5rem 1rem; }
.share-note { font-size: .85rem; margin-top: .2rem; }
.share-toggle { display: inline-flex; align-items: center; gap: .45rem; color: var(--muted); font-size: .8rem; cursor: pointer; white-space: nowrap; padding-top: .2rem; }
.share-body { display: grid; grid-template-columns: minmax(90px, .85fr) minmax(0, 1.15fr); gap: clamp(.6rem, 2vw, 1.6rem); align-items: center; max-width: 52rem; margin: .75rem auto 0; }
.share-graphic {
  position: relative; width: 100%; max-width: 224px; aspect-ratio: 1; justify-self: center; isolation: isolate;
}
.share-pie { position: relative; width: 100%; height: 100%; z-index: 1; }
.share-total { display: grid; justify-items: center; align-content: center; position: absolute; inset: 24%; pointer-events: none; }
.share-total b { color: var(--text); font: 700 clamp(1.35rem, 2.7vw, 2.4rem)/1 var(--numbers); letter-spacing: -.035em; }
.share-total span { color: var(--muted); font-size: .8rem; margin-top: .32rem; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.share-active-percent { color: var(--text); font: 600 .75rem var(--numbers); margin-top: .2rem; }
.share-active-percent::before { content: ''; display: inline-block; width: .4rem; height: .4rem; margin-inline-end: .25rem; border-radius: 2px; background: var(--slice-color); vertical-align: .1rem; }
.share-key { --share-columns: minmax(0, 1fr) 3.8rem 3.4rem; }
.share-key-head, .share-row { display: grid; grid-template-columns: var(--share-columns); align-items: center; gap: .5rem; padding-inline: .5rem; text-align: right; }
.share-key-head { color: var(--muted); font-size: .74rem; padding-block: .35rem; border-bottom: 1px solid var(--line); }
.share-key-head span:first-child { text-align: left; }
.share-legend { list-style: none; margin: .2rem 0 0; padding: 0; }
/* 展开后 20 多行，限高滚动，免得把整张卡片撑得很长 */
.share-legend--expanded { max-height: 20rem; overflow-y: auto; scrollbar-gutter: stable; overscroll-behavior: contain; }
.share-row { width: 100%; min-height: 2.15rem; border: 0; background: transparent; color: var(--text); padding-block: .25rem; font-size: .875rem; cursor: pointer; transition: background-color .16s ease; }
.share-row.active, .share-row:hover { background: color-mix(in srgb, var(--text) 6%, var(--panel)); color: var(--text); }
.share-row--group { position: sticky; top: 0; z-index: 1; background: var(--panel); border-bottom: 1px solid var(--line); }
.share-row--sub { min-height: 1.95rem; font-size: .8125rem; }
.share-row--sub .share-name { padding-left: .85rem; }
.share-row--sub .share-name i { width: .4rem; height: .4rem; }
.share-name { display: grid; grid-template-columns: .5rem auto minmax(0, 1fr); align-items: center; gap: .3rem; text-align: left; white-space: normal; overflow-wrap: anywhere; }
.share-name i { width: .48rem; height: .48rem; border-radius: 2px; }
.share-name img { object-fit: contain; }
.share-name > span { grid-column: 3; }
.share-chevron { margin-inline-start: .3rem; color: var(--muted); vertical-align: -.12rem; transition: transform .16s ease; }
.share-chevron--open { transform: rotate(180deg); }
/* 注意别写成 :global(:root…) .x —— Vue 会丢掉 :global() 之后的部分，把滤镜加到整个 :root 上。 */
:root[data-theme="light"] .share-name img { filter: brightness(0) opacity(.82); }
.share-layers, .share-percent { font-family: var(--numbers); font-variant-numeric: tabular-nums; }
.share-layers { color: var(--muted); }
.share-percent { color: var(--text); font-weight: 650; }
.share-row--sub .share-percent { font-weight: 600; color: var(--text-2); }
.share-empty { margin-top: 1rem; }
/* 展开时被折叠的盟约逐行淡入下滑（按行错开一点点），收起时直接消失，不拖泥带水。 */
.share-item-enter-active { transition: opacity .28s ease, transform .28s cubic-bezier(.2, .8, .2, 1); transition-delay: var(--enter-delay, 0ms); }
.share-item-enter-from { opacity: 0; transform: translateY(-6px); }
.share-item-leave-active { display: none; }
.share-total b, .share-total span { transition: color .16s ease; }
.share-toggle :deep(.n-switch) { flex: none; }
@media (prefers-reduced-motion: reduce) {
  .share-chevron, .share-row { transition: none; }
  .share-item-enter-active { transition: none; }
}
/* 按面板自身宽度（而不是视口）切换：两栏并排时面板可能只有 400px 左右，图例名字会被挤成一字一行。 */
@container (max-width: 520px) {
  .share-body { grid-template-columns: minmax(0, 1fr); gap: .6rem; }
  .share-graphic { max-width: 180px; }
  .share-name { white-space: nowrap; overflow-wrap: normal; }
  .share-name > span { overflow: hidden; text-overflow: ellipsis; }
}
</style>
