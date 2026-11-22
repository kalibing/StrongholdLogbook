<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NCheckbox, NDatePicker, NSelect } from 'naive-ui'
import { logbook, newFilters } from '../context'
import { compareDifficulty, difficultyLabel, playRank, protocolLabel } from '../format'

const { filters, facets } = logbook()
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

const pad = (value: number) => String(value).padStart(2, '0')
const toTimestamp = (value: string) => {
  if (!value) return null
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day).getTime()
}
const toDate = (timestamp: number) => {
  const date = new Date(timestamp)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

const range = computed<[number, number] | null>({
  get() {
    const start = toTimestamp(filters.start)
    const end = toTimestamp(filters.end)
    return start && end ? [start, end] : null
  },
  set(value) {
    filters.start = value ? toDate(value[0]) : ''
    filters.end = value ? toDate(value[1]) : ''
  },
})

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
  <div class="filters" role="group" aria-label="战绩筛选">
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
    <label class="filter-field date-range-field">开局日期
      <NDatePicker v-model:value="range" type="daterange" size="small" clearable
        :actions="['clear', 'confirm']" start-placeholder="开始日期" end-placeholder="结束日期"
        aria-label="开局日期范围" />
    </label>
    <slot name="extra" />
    <div class="filter-actions">
      <NCheckbox v-model:checked="excludeExits">排除疑似直接退出</NCheckbox>
      <NButton size="small" quaternary @click="Object.assign(filters, newFilters())">清空筛选</NButton>
    </div>
  </div>
</template>
