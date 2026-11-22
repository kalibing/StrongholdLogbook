<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logbook } from '../context'
import { query, rolePath, useResource } from '../api'
import { number, shortTime } from '../format'
import type { MatchDetail, MatchPage, Result } from '../models'
import FiltersBar from '../components/FiltersBar.vue'
import MatchReport from '../components/MatchReport.vue'

const { role, filters, revision } = logbook()
const PAGE_SIZE = 10
const result = ref<Result | ''>('')
const page = ref(1)
const detailUrl = ref<string | null>(null)

const listUrl = rolePath(role, () => '/matches' + query(filters, {
  result: result.value,
  page: String(page.value),
  limit: String(PAGE_SIZE),
}))
const { data, pending, error, refresh } = useResource<MatchPage>(listUrl, revision)
const report = useResource<MatchDetail>(detailUrl, revision)

const pages = computed(() => data.value?.pages ?? 1)
const current = computed(() => data.value?.page ?? page.value)
const total = computed(() => data.value?.total ?? 0)

function go(delta: number) {
  const next = current.value + delta
  if (next >= 1 && next <= pages.value) page.value = next
}

function open(id: string) {
  if (role.value) detailUrl.value = '/roles/' + role.value.id + '/matches/' + id
}

function close() {
  detailUrl.value = null
}

watch(filters, () => { page.value = 1 })
watch(result, () => { page.value = 1 })
</script>

<template>
  <FiltersBar>
    <template #extra>
      <label class="filter-field">战果
        <span class="select-field">
          <select v-model="result" aria-label="筛选胜负">
            <option value="">全部结果</option>
            <option value="win">胜</option>
            <option value="loss">负</option>
          </select>
        </span>
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
            <th scope="col">发起者</th>
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
            <td data-label="难度 / 等级">{{ row.difficulty }}</td>
            <td data-label="开局策略">{{ row.strategy ?? '—' }}</td>
            <td data-label="发起者">{{ row.initiator ?? '—' }}</td>
            <td data-label="回合">{{ number(row.rounds) }}</td>
            <td data-label="击杀">{{ number(row.kills) }}</td>
            <td data-label="金币花费">{{ number(row.coins) }}</td>
            <td data-label="盟约总层数">{{ number(row.bond_layers) }}</td>
            <td><button type="button" @click="open(row.id)">查看详情</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="!data?.matches.length" class="empty-state">
      <span>当前筛选范围内没有对局。</span>
      <RouterLink class="button-link" to="/archive">前往档案管理</RouterLink>
    </div>
    <div class="paging">
      <button type="button" :disabled="current <= 1" @click="go(-1)">上一页</button>
      <span>第 {{ current }} / {{ pages }} 页</span>
      <button type="button" :disabled="current >= pages" @click="go(1)">下一页</button>
    </div>
  </section>

  <MatchReport v-if="detailUrl" :detail="report.data.value" :pending="report.pending.value"
    :error="report.error.value" @close="close" />
</template>
