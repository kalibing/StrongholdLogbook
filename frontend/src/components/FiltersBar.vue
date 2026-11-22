<script setup lang="ts">
import { computed } from 'vue'
import { logbook, newFilters } from '../context'
import { protocolLabel } from '../format'

const { filters, facets } = logbook()
const unique = (values: string[]) => [...new Set(values)]
const protocols = computed(() => unique(facets.value.map(item => item.protocol)))
const inProtocol = computed(() => facets.value.filter(item => !filters.protocol || item.protocol === filters.protocol))
const plays = computed(() => unique(inProtocol.value.map(item => item.play)))
const difficulties = computed(() => unique(inProtocol.value.filter(item => !filters.play || item.play === filters.play)
  .map(item => item.difficulty)))
const excludeExits = computed({
  get: () => !filters.include_exits,
  set: (value: boolean) => { filters.include_exits = !value },
})
</script>

<template>
  <div class="filters" role="group" aria-label="战绩筛选">
    <label class="filter-field">协议期
      <span class="select-field">
        <select v-model="filters.protocol" aria-label="协议期" @change="filters.play = ''; filters.difficulty = ''">
          <option value="">全部协议</option>
          <option v-for="value in protocols" :key="value" :value="value">{{ protocolLabel(value) }}</option>
        </select>
      </span>
    </label>
    <label class="filter-field">模拟方式
      <span class="select-field">
        <select v-model="filters.play" aria-label="模拟方式" @change="filters.difficulty = ''">
          <option value="">全部方式</option>
          <option v-for="value in plays" :key="value">{{ value }}</option>
        </select>
      </span>
    </label>
    <label class="filter-field">难度 / 等级
      <span class="select-field">
        <select v-model="filters.difficulty" aria-label="难度或等级">
          <option value="">全部难度 / 等级</option>
          <option v-for="value in difficulties" :key="value">{{ value }}</option>
        </select>
      </span>
    </label>
    <div class="filter-field date-group" role="group" aria-label="开局日期范围">
      <span>开局日期</span>
      <div>
        <input v-model="filters.start" aria-label="起始日期" type="date">
        <span>至</span>
        <input v-model="filters.end" aria-label="结束日期" type="date">
      </div>
    </div>
    <slot name="extra" />
    <label class="exit"><input v-model="excludeExits" type="checkbox"> 排除疑似直接退出</label>
    <button type="button" class="clear-filters" @click="Object.assign(filters, newFilters())">清空筛选</button>
  </div>
</template>
