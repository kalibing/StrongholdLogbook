<script setup lang="ts">
import { computed } from 'vue'
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

function setRange(value: string | string[] | null) {
  const [start = '', end = ''] = Array.isArray(value) ? value : []
  filters.start = start
  filters.end = end
}

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
      <NDatePicker :formatted-value="range" type="daterange" size="small" clearable
        value-format="yyyy-MM-dd" :actions="['clear', 'confirm']"
        start-placeholder="开始日期" end-placeholder="结束日期" aria-label="开局日期范围"
        @update:formatted-value="setRange" />
    </label>
    <slot name="extra" />
    <div class="filter-actions">
      <NCheckbox v-model:checked="excludeExits">排除疑似直接退出</NCheckbox>
      <NButton size="small" quaternary @click="clearFilters">清空筛选</NButton>
    </div>
  </div>
</template>
