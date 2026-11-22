<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { logbook } from '../context'
import { query, rolePath, useResource } from '../api'
import { dateTime, number, protocolLabel, resultLabel } from '../format'
import type { MatchDetail, MatchPage, Result } from '../models'
import Feedback from '../components/Feedback.vue'
import FiltersBar from '../components/FiltersBar.vue'
import MatchReport from '../components/MatchReport.vue'

const { role, filters, revision } = logbook()
const PAGE_SIZE = 12
const tabs: { value: Result | ''; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'win', label: '胜' },
  { value: 'loss', label: '负' },
]
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

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && detailUrl.value) close()
}

watch(filters, () => { page.value = 1 })
watch(result, () => { page.value = 1 })
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <FiltersBar />
  <div class="toolbar">
    <div class="tabs" role="group" aria-label="按战果筛选">
      <button v-for="tab in tabs" :key="tab.label" type="button"
        :aria-pressed="result === tab.value" @click="result = tab.value">
        {{ tab.label }}
      </button>
    </div>
    <p class="muted">{{ total }} 局记录 · 每页 {{ PAGE_SIZE }} 局</p>
  </div>

  <Feedback v-if="pending" pending />
  <Feedback v-else-if="error" :error="error" @retry="refresh" />
  <template v-else-if="data?.matches.length">
    <div class="match-list">
      <button v-for="row in data.matches" :key="row.id" type="button" class="match-row" @click="open(row.id)">
        <div class="match-main">
          <div class="match-title">
            <span class="tag" :class="{ loss: row.result === 'loss' }">{{ resultLabel(row.result) }}</span>
            <strong>{{ dateTime(row.played_at) }}</strong>
            <span v-if="row.suspected_exit" class="tag exit">疑似退出</span>
          </div>
          <div class="match-meta">
            <span>{{ protocolLabel(row.protocol) }}</span>
            <span>{{ row.play }}</span>
            <span>{{ row.difficulty }}</span>
            <span v-if="row.scenario">{{ row.scenario }}</span>
            <span v-if="row.strategy">{{ row.strategy }}<template v-if="row.initiator"> · {{ row.initiator }}</template></span>
          </div>
        </div>
        <div class="match-stats">
          <span>{{ number(row.rounds) }}<small>回合</small></span>
          <span>{{ number(row.kills) }}<small>击杀</small></span>
          <span>{{ number(row.coins) }}<small>金币</small></span>
          <span>{{ number(row.bond_layers) }}<small>盟约层</small></span>
        </div>
      </button>
    </div>
    <nav class="pager" aria-label="分页">
      <button type="button" :disabled="current <= 1" @click="go(-1)">上一页</button>
      <span>第 {{ current }} / {{ pages }} 页</span>
      <button type="button" :disabled="current >= pages" @click="go(1)">下一页</button>
    </nav>
  </template>
  <Feedback v-else empty="当前筛选范围内没有对局。可调整筛选，或导入一份战绩文件。">
    <RouterLink class="button-link" to="/archive">前往档案管理</RouterLink>
  </Feedback>

  <MatchReport v-if="detailUrl" :detail="report.data.value" :pending="report.pending.value"
    :error="report.error.value" @close="close" />
</template>
