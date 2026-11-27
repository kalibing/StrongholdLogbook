<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NRadioButton, NRadioGroup } from 'naive-ui'
import { logbook, newFilters } from '../context'
import { query, useResource } from '../api'
import TierTag from '../components/TierTag.vue'
import { difficultyLabel, number, shortTime } from '../format'
import { strategyIcon, strategyOf, unitOf } from '../bands'
import type { MatchDetail, MatchPage, MatchSummary, Result } from '../models'
import FiltersBar from '../components/FiltersBar.vue'
import HoverTip from '../components/HoverTip.vue'
import MatchReport from '../components/MatchReport.vue'
import ListPagination from '../components/ListPagination.vue'

const { filters, revision } = logbook()
const pageSize = ref(10)
const result = ref<Result | ''>('')
const resultOptions: { label: string; value: Result | '' }[] = [
  { label: '全部', value: '' }, { label: '胜', value: 'win' }, { label: '负', value: 'loss' },
]
const page = ref(1)
const detailUrl = ref<string | null>(null)
/** 分队（发起干员）名：优先用记录里的发起者，其次从 band 映射推出。 */
function rowUnitName(row: MatchSummary) {
  return row.initiator || unitOf(row.strategy)
}

const listUrl = computed(() => '/matches' + query(filters, {
  result: result.value,
  page: String(page.value),
  limit: String(pageSize.value),
}))
const { data, pending, error, resolvedUrl, refresh } = useResource<MatchPage>(listUrl, revision, true)
const report = useResource<MatchDetail>(detailUrl, revision)

const pages = computed(() => data.value?.pages ?? 1)
const current = computed(() => data.value?.page ?? page.value)
const total = computed(() => data.value?.total ?? 0)
const displayedPageSize = computed(() => Number(new URLSearchParams(resolvedUrl.value?.split('?')[1]).get('limit')) || pageSize.value)
const hasFilters = computed(() => Boolean(result.value || Object.values(filters).some(Boolean)))

function resetFilters() {
  Object.assign(filters, newFilters())
  result.value = ''
}

function open(id: string) {
  detailUrl.value = '/matches/' + id
}

function close() {
  detailUrl.value = null
}

function changePageSize(size: number) {
  pageSize.value = size
  page.value = 1
}

watch(filters, () => { page.value = 1 })
watch(result, () => { page.value = 1 })
</script>

<template>
  <FiltersBar @reset="result = ''" />

  <section class="panel table-panel" aria-labelledby="history-title">
    <div class="split table-heading history-heading">
      <div class="history-title">
        <h2 id="history-title">结算列表</h2>
        <span v-if="pending" class="period" role="status">正在读取对局…</span>
        <span v-else-if="data" class="period">{{ total }} 局</span>
      </div>
      <NRadioGroup :value="result" size="small" name="history-result" aria-label="筛选战果"
        @update:value="(value: Result | '') => result = value">
        <NRadioButton v-for="option in resultOptions" :key="option.value" :value="option.value" :label="option.label" />
      </NRadioGroup>
    </div>
    <p v-if="error" class="table-feedback load-message" role="alert">
      {{ error }} <span v-if="data">正在显示上次成功的结果。</span> <button type="button" @click="refresh">重试</button>
    </p>
    <div v-if="data?.matches.length" class="scroll history-table-wrap" :aria-busy="pending"
      :style="{ '--history-empty-rows': pages > 1 ? displayedPageSize - data.matches.length : 0 }">
      <table class="history-table">
        <colgroup>
          <col class="history-time-col">
          <col class="history-result-col">
          <col class="history-mode-col">
          <col class="history-tier-col">
          <col class="history-strategy-col">
          <col class="history-small-col" span="2">
          <col class="history-value-col" span="2">
        </colgroup>
        <thead>
          <tr>
            <th scope="col">开局时间</th>
            <th scope="col">战果</th>
            <th scope="col">模拟方式</th>
            <th scope="col">难度 / 等级</th>
            <th scope="col">策略</th>
            <th scope="col">回合</th>
            <th scope="col">击杀</th>
            <th scope="col">金币花费</th>
            <th scope="col">盟约总层数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data?.matches ?? []" :key="row.id" class="match-row" tabindex="0"
            @click="open(row.id)" @keydown.enter.prevent="open(row.id)" @keydown.space.prevent="open(row.id)">
            <td>{{ shortTime(row.played_at) }}</td>
            <td><span class="chip" :class="{ loss: row.result === 'loss' }">{{ row.result === 'win' ? '胜' : '负' }}</span></td>
            <td data-label="模拟方式">{{ row.play }}</td>
            <td data-label="难度 / 等级"><TierTag :label="difficultyLabel(row.difficulty)" /></td>
            <HoverTip as="td" data-label="策略" :text="rowUnitName(row)">
              <span class="strategy-cell">
                <img v-if="strategyIcon(row.strategy)" class="strategy-icon" :src="strategyIcon(row.strategy)" alt="">
                <span class="strategy-name">{{ strategyOf(row.strategy) || '—' }}</span>
              </span>
            </HoverTip>
            <td data-label="回合">{{ number(row.rounds) }}</td>
            <td data-label="击杀">{{ number(row.kills) }}</td>
            <td data-label="金币花费">{{ number(row.coins) }}</td>
            <td data-label="盟约总层数">{{ number(row.bond_layers) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="data && !data.matches.length && !pending && !error" class="empty-state">
      <span>当前筛选范围内没有对局。</span>
      <NButton v-if="hasFilters" secondary @click="resetFilters">清空筛选</NButton>
      <RouterLink v-else class="button-link" to="/import">前往数据导入</RouterLink>
    </div>
    <ListPagination v-if="total" :page="current" :page-size="displayedPageSize" :total="total"
      :disabled="pending" @update:page="page = $event" @update:page-size="changePageSize" />
  </section>

  <MatchReport v-if="detailUrl" :detail="report.data.value" :pending="report.pending.value"
    :error="report.error.value" @close="close" @retry="report.refresh" />
</template>

<style scoped>
.history-heading { flex-wrap: wrap; gap: .5rem 1rem; }
.history-title { display: flex; align-items: baseline; gap: .75rem; }
</style>
