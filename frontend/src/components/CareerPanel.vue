<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logbook } from '../context'
import { query, useResource } from '../api'
import { number, resultLabel } from '../format'
import type { Career } from '../models'
import TierTag from './TierTag.vue'

// 战绩总览「生涯档案」：跟随筛选条件的最高通关、连胜、生涯纪录与近一年活跃度。
const { filters, revision } = logbook()
const url = computed(() => '/career' + query(filters))
const { data, pending, error, refresh } = useResource<Career>(url, revision, true)

function duration(seconds: number | null) {
  if (seconds == null) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  return hours ? `${hours} 小时 ${minutes} 分` : `${minutes} 分`
}

const tiles = computed(() => {
  const career = data.value?.career
  const streaks = data.value?.streaks
  if (!career || !streaks) return []
  const current = streaks.current
  return [
    { label: '活跃天数', value: number(career.active_days), hint: career.first_day ? `${career.first_day} 起` : '' },
    { label: '累计时长', value: duration(career.play_seconds), hint: '有时长记录的对局' },
    { label: '最长连胜', value: `${streaks.best_win} 局`, hint: '' },
    {
      label: '当前状态', value: current ? `${current.count} 连${resultLabel(current.result)}` : '—',
      hint: career.last_day ? `最近一局 ${career.last_day}` : '', loss: current?.result === 'loss',
    },
  ]
})

const records = computed(() => {
  const career = data.value?.career
  if (!career) return []
  return [
    { label: '最高击杀', hint: '单局最高击杀', value: number(career.max_kills) },
    { label: '最高盟约层数', hint: '单局最高盟约总层数', value: career.max_layers == null ? '—' : `${career.max_layers} 层` },
    { label: '累计击杀', hint: '筛选范围内击杀之和', value: number(career.total_kills) },
  ]
})

/** 活跃热力图：按周分列，周一在上；颜色按当天局数分四档。 */
const heat = computed(() => (data.value?.activity.days ?? []).map(entry => ({
  ...entry, level: entry.count === 0 ? 0 : entry.count <= 2 ? 1 : entry.count <= 4 ? 2 : entry.count <= 7 ? 3 : 4,
})))
const activeDays = computed(() => heat.value.filter(entry => entry.count).length)

// 窄屏时热力图横向滚动：默认停在最右（最近几周），而不是一年前的空白。
const heatWrap = ref<HTMLElement | null>(null)
watch(heatWrap, element => { if (element) element.scrollLeft = element.scrollWidth })
</script>

<template>
  <p v-if="error" class="load-message" role="alert">
    {{ error }} <span v-if="data">正在显示上次成功的结果。</span> <button type="button" @click="refresh">重试</button>
  </p>
  <p v-if="pending && !data" class="load-message" role="status">正在读取生涯档案…</p>

  <div v-if="data" class="career" :aria-busy="pending">
    <div class="career-grid">
      <section class="panel career-card" aria-labelledby="career-best">
        <h2 id="career-best">最高通关</h2>
        <dl class="career-boxes career-boxes--two">
          <div><dt>联合模拟</dt><dd><TierTag v-if="data.best.union" :label="data.best.union" :size="26" /><span v-else class="muted">暂无</span></dd></div>
          <div><dt>独立模拟</dt><dd><TierTag v-if="data.best.solo" :label="data.best.solo" :size="26" /><span v-else class="muted">暂无</span></dd></div>
        </dl>
      </section>
      <section class="panel career-card" aria-labelledby="career-records">
        <h2 id="career-records">生涯纪录</h2>
        <dl class="career-boxes career-boxes--three">
          <div v-for="record in records" :key="record.label" :title="record.hint"><dt>{{ record.label }}</dt><dd class="career-number">{{ record.value }}</dd></div>
        </dl>
      </section>
    </div>

    <section class="career-tiles" aria-label="连胜与活跃">
      <div v-for="tile in tiles" :key="tile.label" class="panel career-tile">
        <span class="career-tile-label">{{ tile.label }}</span>
        <strong :class="{ 'career-loss': tile.loss }">{{ tile.value }}</strong>
        <small v-if="tile.hint" class="muted">{{ tile.hint }}</small>
      </div>
    </section>

    <section class="panel career-card" aria-labelledby="career-activity">
      <div class="split">
        <h2 id="career-activity">活跃度</h2>
        <span class="period">{{ data.activity.start }} — {{ data.activity.end }} · {{ activeDays }} 天有对局</span>
      </div>
      <div ref="heatWrap" class="career-heat-wrap">
        <ol class="career-heat-days" aria-hidden="true"><li>一</li><li></li><li>三</li><li></li><li>五</li><li></li><li>日</li></ol>
        <ol class="career-heat">
          <li v-for="entry in heat" :key="entry.day" :class="`heat-${entry.level}`" :title="`${entry.day} · ${entry.count} 局`">
            <span class="sr-only">{{ entry.day }} {{ entry.count }} 局</span>
          </li>
        </ol>
      </div>
      <p class="career-heat-legend muted" aria-hidden="true">
        少 <i class="heat-0"></i><i class="heat-1"></i><i class="heat-2"></i><i class="heat-3"></i><i class="heat-4"></i> 多
      </p>
    </section>
  </div>
</template>

<style scoped>
.career { display: grid; gap: 1rem; }
.career h2 { font-size: 1.1rem; }
.career-card { padding: 1.1rem 1.25rem 1.25rem; }
.career-card .split { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
.career-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }

.career-boxes { display: grid; gap: .75rem; margin-top: .8rem; }
.career-boxes--two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.career-boxes--three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.career-boxes > div { min-width: 0; padding: .75rem .9rem; border: 1px solid var(--line); border-radius: 2px; background: var(--inset); }
.career-boxes dt { overflow: hidden; margin-bottom: .35rem; color: var(--muted); font-size: .8rem; white-space: nowrap; text-overflow: ellipsis; }
.career-boxes dd { font-weight: 700; font-size: 1.05rem; }
.career-number { font: 700 1.2rem var(--numbers) !important; }

.career-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem; }
.career-tile { display: grid; align-content: start; gap: .3rem; padding: .9rem 1rem; }
.career-tile-label { color: var(--muted); font-size: .8rem; }
.career-tile strong { font: 700 1.45rem/1.15 var(--numbers); white-space: nowrap; }
.career-tile small { font-size: .74rem; }
.career-loss { color: var(--loss); }

/* —— 活跃热力图：一年 53 列铺满面板宽度；窄屏时每格至少 10px，横向滚动 —— */
.career-heat-wrap { display: flex; gap: .4rem; margin-top: .9rem; overflow-x: auto; padding-bottom: .25rem; }
.career-heat-days, .career-heat { margin: 0; padding: 0; list-style: none; display: grid; grid-template-rows: repeat(7, 1fr); gap: 3px; }
.career-heat-days { position: sticky; left: 0; z-index: 1; flex: none; padding-right: .3rem; background: var(--panel); color: var(--muted); font-size: .68rem; align-items: center; }
.career-heat { flex: 1; min-width: calc(53 * 13px); grid-auto-flow: column; grid-auto-columns: minmax(10px, 1fr); }
.career-heat li { aspect-ratio: 1; border-radius: 2px; }
.career-heat-legend { display: flex; align-items: center; justify-content: flex-end; gap: 4px; margin-top: .5rem; font-size: .74rem; }
.career-heat-legend i { display: inline-block; width: 12px; height: 12px; border-radius: 2px; }
.heat-0 { background: var(--inset); outline: 1px solid color-mix(in srgb, var(--line) 70%, transparent); outline-offset: -1px; }
.heat-1 { background: color-mix(in srgb, var(--accent) 28%, var(--inset)); }
.heat-2 { background: color-mix(in srgb, var(--accent) 52%, var(--inset)); }
.heat-3 { background: color-mix(in srgb, var(--accent) 76%, var(--inset)); }
.heat-4 { background: var(--accent); }

.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

@media (prefers-reduced-motion: no-preference) {
  .career-heat li { animation: career-pop .4s ease-out both; }
}
@keyframes career-pop { from { opacity: 0; transform: scale(.4); } }

@media (max-width: 980px) {
  .career-grid { grid-template-columns: 1fr; }
}
@media (max-width: 730px) {
  .career-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .career-boxes--three { grid-template-columns: 1fr; }
}
</style>
