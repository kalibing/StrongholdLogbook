<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NCheckbox, NDatePicker, NSelect } from 'naive-ui'
import { logbook, newFilters } from '../context'
import { compareDifficulty, difficultyLabel, playRank, protocolLabel } from '../format'

const { filters, facets } = logbook()
const emit = defineEmits<{ reset: [] }>()
const unique = (values: string[]) => [...new Set(values)]
const protocols = computed(() => unique(facets.value.map(item => item.protocol)))
const inProtocol = computed(() => facets.value.filter(item => !filters.protocol || item.protocol === filters.protocol))
const plays = computed(() => unique(inProtocol.value.map(item => item.play)).sort((a, b) => playRank(a) - playRank(b)))
const difficulties = computed(() => unique(inProtocol.value.filter(item => !filters.play || item.play === filters.play)
  .map(item => item.difficulty)).sort(compareDifficulty))

const protocolOptions = computed(() => [
  { label: '全部协议', value: '' },
  ...protocols.value.map(value => ({ label: protocolLabel(value), value })),
])
const playOptions = computed(() => [{ label: '全部方式', value: '' }, ...plays.value.map(value => ({ label: value, value }))])
const difficultyOptions = computed(() => [
  { label: '全部难度 / 等级', value: '' },
  ...difficulties.value.map(value => ({ label: difficultyLabel(value), value })),
])

const excludeExits = computed({
  get: () => !filters.include_exits,
  set: (value: boolean) => { filters.include_exits = !value },
})

const range = computed<[string, string] | null>(() => filters.start && filters.end ? [filters.start, filters.end] : null)

/** 北京时间的日期（yyyy-MM-dd）：后端按 UTC+8 归档，快捷区间也必须用同一时区，否则海外时区会错一天。 */
const DAY = 86_400_000
function localDate(offsetDays = 0): string {
  return new Date(Date.now() + 8 * 3_600_000 + offsetDays * DAY).toISOString().slice(0, 10)
}

/** 只允许选到明天（北京时间），更晚的日期在面板里直接禁用。每次调用都重新取当天，跨午夜不会过期。 */
function disabledDate(timestamp: number): boolean {
  const picked = new Date(timestamp)
  const pickedDay = `${picked.getFullYear()}-${String(picked.getMonth() + 1).padStart(2, '0')}-${String(picked.getDate()).padStart(2, '0')}`
  return pickedDay > localDate(1)
}

const presets: { label: string; days: number | null }[] = [
  { label: '今天', days: 0 },
  { label: '近 7 天', days: 6 },
  { label: '近 30 天', days: 29 },
  { label: '全部', days: null },
]
const activePreset = computed(() => presets.find(preset => isPreset(preset.days))?.label ?? '')
function isPreset(days: number | null): boolean {
  if (days === null) return !filters.start && !filters.end
  return filters.start === localDate(-days) && filters.end === localDate(0)
}
function applyPreset(days: number | null) {
  if (days === null) {
    filters.start = ''
    filters.end = ''
    return
  }
  filters.start = localDate(-days)
  filters.end = localDate(0)
}

function setRange(value: string | string[] | null) {
  const [rawStart = '', rawEnd = ''] = Array.isArray(value) ? value : []
  const maxDate = localDate(1)
  filters.start = rawStart > maxDate ? maxDate : rawStart
  filters.end = rawEnd > maxDate ? maxDate : rawEnd
}

/** 手机上筛选栏默认收起，只露一行摘要，展开后才是完整表单。桌面始终展开（由 CSS 控制）。 */
const expanded = ref(false)
const activeCount = computed(() => [filters.protocol, filters.play, filters.difficulty, filters.start || filters.end, filters.include_exits]
  .filter(Boolean).length)

function clearFilters() {
  Object.assign(filters, newFilters())
  emit('reset')
}

function changeProtocol(value: string) {
  filters.protocol = value
  filters.play = ''
  filters.difficulty = ''
}

function changePlay(value: string) {
  filters.play = value
  filters.difficulty = ''
}
</script>

<template>
  <div class="filters" :class="{ 'filters--open': expanded }" role="group" aria-label="战绩筛选">
    <button type="button" class="filters-toggle" :aria-expanded="expanded" @click="expanded = !expanded">
      <span>筛选</span>
      <small>{{ activeCount ? `已设 ${activeCount} 项` : '全部对局' }}{{ activePreset && activePreset !== '全部' ? ` · ${activePreset}` : '' }}</small>
      <i aria-hidden="true">{{ expanded ? '收起' : '展开' }}</i>
    </button>
    <label class="filter-field">协议期
      <NSelect :value="filters.protocol" :options="protocolOptions" size="small" aria-label="协议期"
        @update:value="changeProtocol" />
    </label>
    <label class="filter-field">模拟方式
      <NSelect :value="filters.play" :options="playOptions" size="small" aria-label="模拟方式"
        @update:value="changePlay" />
    </label>
    <label class="filter-field">难度 / 等级
      <NSelect :value="filters.difficulty" :options="difficultyOptions" size="small" aria-label="难度或等级"
        @update:value="value => filters.difficulty = value" />
    </label>
    <div class="filter-field date-range-field">
      <span class="filter-label">开局日期</span>
      <div class="date-range-row">
        <span class="date-picker-wrap">
          <NDatePicker :formatted-value="range" type="daterange" size="small" clearable
            value-format="yyyy-MM-dd" :actions="['clear', 'confirm']" :is-date-disabled="disabledDate"
            start-placeholder="开始日期" end-placeholder="结束日期" aria-label="开局日期范围"
            @update:formatted-value="setRange" />
        </span>
        <div class="date-presets" role="group" aria-label="快捷区间">
          <NButton v-for="preset in presets" :key="preset.label" size="tiny" :type="activePreset === preset.label ? 'primary' : 'default'"
            :aria-pressed="activePreset === preset.label" @click="applyPreset(preset.days)">{{ preset.label }}</NButton>
        </div>
      </div>
    </div>
    <slot name="extra" />
    <div class="filter-actions">
      <NCheckbox v-model:checked="excludeExits">排除疑似直接退出</NCheckbox>
      <NButton size="small" quaternary @click="clearFilters">清空筛选</NButton>
    </div>
  </div>
</template>

<style scoped>
.filters-toggle { display: none; }
@media (max-width: 730px) {
  .filters-toggle {
    grid-column: 1 / -1; display: flex; align-items: center; gap: .6rem; width: 100%;
    min-height: 2.25rem; padding: 0; border: 0; background: transparent; color: var(--text); text-align: left;
  }
  .filters-toggle span { font-weight: 650; }
  .filters-toggle small { flex: 1; min-width: 0; color: var(--muted); font-size: .8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .filters-toggle i { font-style: normal; color: var(--accent); font-size: .8rem; }
  .filters:not(.filters--open) > :not(.filters-toggle) { display: none; }
}
</style>
