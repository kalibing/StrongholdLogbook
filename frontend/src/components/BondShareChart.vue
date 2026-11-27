<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { BOND_ICONS } from '../assets'
import { logbook } from '../context'
import { number, percent } from '../format'
import type { BondLayers } from '../models'

echarts.use([PieChart, TooltipComponent, CanvasRenderer])

const props = defineProps<{ bonds: BondLayers[]; description: string }>()
const titleId = useId()
const { theme } = logbook()
const container = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
const colors = ['#628ef5', '#36bda3', '#a486ef', '#f5b552', '#45a9d1', '#eb7f9c', '#8593ae']
const previewIndex = ref<number | null>(null)
const selectedIndex = ref<number | null>(null)
const activeIndex = computed(() => previewIndex.value ?? selectedIndex.value)
const total = computed(() => props.bonds.reduce((sum, bond) => sum + bond.layers, 0))
const slices = computed(() => {
  const major = props.bonds.slice(0, 6)
  const rest = props.bonds.slice(6)
  if (rest.length === 1) major.push(rest[0])
  if (rest.length > 1) {
    major.push({ name: `其他 ${rest.length} 种`, layers: rest.reduce((sum, bond) => sum + bond.layers, 0) })
  }
  return major.map((bond, index) => ({ ...bond, share: bond.layers / total.value, color: colors[index] }))
})
const activeSlice = computed(() => activeIndex.value === null ? null : slices.value[activeIndex.value])
const shareText = (share: number) => share < .001 ? '<0.1%' : percent(share)

function drawChart() {
  const css = getComputedStyle(document.documentElement)
  const panel = css.getPropertyValue('--panel').trim()
  chart?.setOption({
    animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    tooltip: {
      trigger: 'item', confine: true, renderMode: 'richText',
      formatter: (params: { dataIndex: number } | { dataIndex: number }[]) => {
        const item = Array.isArray(params) ? params[0] : params
        const slice = item && slices.value[item.dataIndex]
        return slice ? `${slice.name}\n${number(slice.layers)} 层 · ${shareText(slice.share)}` : ''
      },
      padding: [7, 10],
      textStyle: { color: css.getPropertyValue('--text').trim(), fontSize: 12 },
      backgroundColor: css.getPropertyValue('--inset').trim(),
      borderColor: css.getPropertyValue('--control-line').trim(),
    },
    series: [{
      type: 'pie', radius: ['68%', '88%'], startAngle: 90, label: { show: false },
      itemStyle: { borderColor: panel, borderWidth: 2, borderRadius: 4 },
      emphasis: { focus: 'self', scaleSize: 4 },
      blur: { itemStyle: { opacity: .32 } },
      data: slices.value.map(slice => ({
        name: slice.name, value: slice.layers,
        itemStyle: { color: slice.color },
      })),
    }],
  })
}

function toggle(index: number) {
  selectedIndex.value = selectedIndex.value === index ? null : index
}

watch(container, (element, _, onCleanup) => {
  if (!element) return
  const instance = echarts.init(element)
  chart = instance
  instance.on('mouseover', 'series.pie', event => { previewIndex.value = event.dataIndex })
  instance.on('mouseout', 'series.pie', () => { previewIndex.value = null })
  instance.on('click', 'series.pie', event => { toggle(event.dataIndex) })
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
})
watch(activeIndex, (index, previous) => {
  if (previous !== null) chart?.dispatchAction({ type: 'downplay', seriesIndex: 0, dataIndex: previous })
  if (index !== null) chart?.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: index })
})
</script>

<template>
  <section class="panel bond-share" :aria-labelledby="titleId" @keydown.escape="selectedIndex = null; previewIndex = null">
    <header>
      <h2 :id="titleId">盟约层数分布</h2>
      <p class="muted share-note">{{ description }}</p>
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
        <ul class="share-legend">
          <li v-for="(slice, index) in slices" :key="slice.name">
            <button type="button" class="share-row" :class="{ active: activeIndex === index }"
              :aria-pressed="selectedIndex === index" :aria-label="`${slice.name}，${number(slice.layers)} 层，占 ${shareText(slice.share)}`"
              @pointerenter="previewIndex = index" @pointerleave="previewIndex = null"
              @focus="previewIndex = index" @blur="previewIndex = null" @click="toggle(index)">
              <span class="share-name">
                <i :style="{ background: slice.color }" aria-hidden="true"></i>
                <img v-if="BOND_ICONS[slice.name]" :src="BOND_ICONS[slice.name]" width="16" height="16" alt="">
                <span>{{ slice.name }}</span>
              </span>
              <span class="share-layers">{{ number(slice.layers) }}</span>
              <b class="share-percent">{{ shareText(slice.share) }}</b>
            </button>
          </li>
        </ul>
      </div>
    </div>
    <p v-else class="muted share-empty">暂无盟约层数记录。</p>
  </section>
</template>

<style scoped>
.bond-share { padding: 1.2rem clamp(1rem, 2.5vw, 1.65rem); }
.share-note { font-size: .85rem; margin-top: .2rem; }
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
.share-row { width: 100%; min-height: 2.15rem; border: 0; background: transparent; color: var(--text); padding-block: .25rem; font-size: .875rem; }
.share-row.active, .share-row:hover { background: color-mix(in srgb, var(--text) 6%, var(--panel)); color: var(--text); }
.share-name { display: grid; grid-template-columns: .5rem auto minmax(0, 1fr); align-items: center; gap: .3rem; text-align: left; white-space: normal; overflow-wrap: anywhere; }
.share-name i { width: .48rem; height: .48rem; border-radius: 2px; }
.share-name img { object-fit: contain; }
.share-name > span { grid-column: 3; }
:global(:root[data-theme="light"]) .share-name img { filter: brightness(0) opacity(.82); }
.share-layers, .share-percent { font-family: var(--numbers); font-variant-numeric: tabular-nums; }
.share-layers { color: var(--muted); }
.share-percent { color: var(--text); font-weight: 650; }
.share-empty { margin-top: 1rem; }
@media (max-width: 440px) {
  .share-body { grid-template-columns: minmax(0, 1fr); gap: .45rem; }
  .share-graphic { max-width: 166px; }
}
</style>
