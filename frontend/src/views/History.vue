<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NPagination, NSelect } from 'naive-ui'
import { logbook } from '../context'
import { query, useResource } from '../api'
import { avatarFor, loadDirectory } from '../directory'
import { difficultyLabel, number, shortTime } from '../format'
import type { MatchDetail, MatchPage, Result } from '../models'
import FiltersBar from '../components/FiltersBar.vue'
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
const { data, pending, error, refresh } = useResource<MatchPage>(listUrl, revision)
const report = useResource<MatchDetail>(detailUrl, revision)

const pages = computed(() => data.value?.pages ?? 1)
const current = computed(() => data.value?.page ?? page.value)
const total = computed(() => data.value?.total ?? 0)

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
  <FiltersBar>
    <template #extra>
      <label class="filter-field">战果
        <NSelect :value="result" :options="resultOptions" size="small" aria-label="筛选胜负"
          @update:value="value => result = value" />
      </label>
    </template>
  </FiltersBar>

  <p v-if="pending" class="load-message" role="status">正在读取对局…</p>
  <p v-else-if="error" class="load-message" role="alert">
    {{ error }} <button type="button" @click="refresh">重试</button>
  </p>

  <section v-else class="panel table-panel" aria-labelledby="history-title">
    <div class="split table-heading">
      <h2 id="history-title">结算列表</h2>
      <span class="period">{{ total }} 局</span>
    </div>
    <div class="scroll">
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
            <td data-label="模拟方式">{{ row.play }}</td>
            <td data-label="难度 / 等级">{{ difficultyLabel(row.difficulty) }}</td>
            <td data-label="开局策略">{{ row.strategy ?? '—' }}</td>
            <td data-label="发起者">
              <span class="with-avatar">
                <img v-if="initiatorAvatar(row.initiator)" :src="initiatorAvatar(row.initiator)!" width="22" height="22" alt="">
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
    <div v-if="!data?.matches.length" class="empty-state">
      <span>当前筛选范围内没有对局。</span>
      <RouterLink class="button-link" to="/archive">前往档案管理</RouterLink>
    </div>
    <div class="paging">
      <NPagination :page="current" :page-count="pages" size="small" @update:page="value => page = value" />
    </div>
  </section>

  <MatchReport v-if="detailUrl" :detail="report.data.value" :pending="report.pending.value"
    :error="report.error.value" @close="close" />
</template>
