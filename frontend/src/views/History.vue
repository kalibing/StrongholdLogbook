<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NPagination, NSelect } from 'naive-ui'
import { logbook, newFilters } from '../context'
import { query, useResource } from '../api'
import { avatarFor, loadDirectory } from '../directory'
import TierTag from '../components/TierTag.vue'
import { difficultyLabel, number, shortTime } from '../format'
import type { MatchDetail, MatchPage, Result } from '../models'
import FiltersBar from '../components/FiltersBar.vue'
import AvatarImage from '../components/AvatarImage.vue'
import MatchReport from '../components/MatchReport.vue'

const { filters, revision } = logbook()
const PAGE_SIZE = 10
const result = ref<Result | ''>('')
const resultOptions = [{ label: '全部结果', value: '' }, { label: '胜', value: 'win' }, { label: '负', value: 'loss' }]
const page = ref(1)
const detailUrl = ref<string | null>(null)
const names = ref(new Map<string, string>())
const initiatorAvatar = (value: string | null) => avatarFor(names.value, value)

const listUrl = computed(() => '/matches' + query(filters, {
  result: result.value,
  page: String(page.value),
  limit: String(PAGE_SIZE),
}))
const { data, pending, error, refresh } = useResource<MatchPage>(listUrl, revision, true)
const report = useResource<MatchDetail>(detailUrl, revision)

const pages = computed(() => data.value?.pages ?? 1)
const current = computed(() => data.value?.page ?? page.value)
const total = computed(() => data.value?.total ?? 0)
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

onMounted(async () => { names.value = await loadDirectory() })
watch(filters, () => { page.value = 1 })
watch(result, () => { page.value = 1 })
</script>

<template>
  <FiltersBar @reset="result = ''">
    <template #extra>
      <label class="filter-field">战果
        <NSelect :value="result" :options="resultOptions" size="small" aria-label="筛选胜负"
          @update:value="value => result = value" />
      </label>
    </template>
  </FiltersBar>

  <section class="panel table-panel" aria-labelledby="history-title">
    <div class="split table-heading">
      <h2 id="history-title">结算列表</h2>
      <span v-if="pending" class="period" role="status">正在读取对局…</span>
      <span v-else-if="data" class="period">{{ total }} 局</span>
    </div>
    <p v-if="error" class="table-feedback load-message" role="alert">
      {{ error }} <button type="button" @click="refresh">重试</button>
    </p>
    <div v-if="data?.matches.length" class="scroll" :aria-busy="pending">
      <table class="history-table">
        <thead>
          <tr>
            <th scope="col">开局时间</th>
            <th scope="col">战果</th>
            <th scope="col">模拟方式</th>
            <th scope="col">难度 / 等级</th>
            <th scope="col">开局策略</th>
            <th scope="col">发起干员</th>
            <th scope="col">回合</th>
            <th scope="col">击杀</th>
            <th scope="col">金币花费</th>
            <th scope="col">盟约总层数</th>
            <th scope="col">战报</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data?.matches ?? []" :key="row.id">
            <td>{{ shortTime(row.played_at) }}</td>
            <td><span class="chip" :class="{ loss: row.result === 'loss' }">{{ row.result === 'win' ? '胜' : '负' }}</span></td>
            <td data-label="模拟方式"><TierTag :label="row.play" /></td>
            <td data-label="难度 / 等级">{{ difficultyLabel(row.difficulty) }}</td>
            <td data-label="开局策略">{{ row.strategy ?? '—' }}</td>
            <td data-label="发起者">
              <span class="with-avatar">
                <AvatarImage v-if="row.initiator" :src="initiatorAvatar(row.initiator)" :name="row.initiator" :size="22" />
                <span>{{ row.initiator ?? '—' }}</span>
              </span>
            </td>
            <td data-label="回合">{{ number(row.rounds) }}</td>
            <td data-label="击杀">{{ number(row.kills) }}</td>
            <td data-label="金币花费">{{ number(row.coins) }}</td>
            <td data-label="盟约总层数">{{ number(row.bond_layers) }}</td>
            <td><NButton size="tiny" quaternary type="primary" @click="open(row.id)">查看详情</NButton></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="data && !data.matches.length && !pending && !error" class="empty-state">
      <span>当前筛选范围内没有对局。</span>
      <NButton v-if="hasFilters" secondary @click="resetFilters">清空筛选</NButton>
      <RouterLink v-else class="button-link" to="/import">前往数据导入</RouterLink>
    </div>
    <div v-if="pages > 1 && data?.matches.length" class="paging">
      <NPagination :page="current" :page-count="pages" size="small" @update:page="value => page = value" />
    </div>
  </section>

  <MatchReport v-if="detailUrl" :detail="report.data.value" :pending="report.pending.value"
    :error="report.error.value" @close="close" @retry="report.refresh" />
</template>
