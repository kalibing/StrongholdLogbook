<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NInput, NRadioButton, NRadioGroup, NSelect } from 'naive-ui'
import { logbook } from '../context'
import { query, useResource } from '../api'
import { percent } from '../format'
import { portrait } from '../icons'
import { strategyIcon, strategyOf, unitOf } from '../bands'
import type { Operator, StrategyStat } from '../models'
import AvatarImage from '../components/AvatarImage.vue'
import FiltersBar from '../components/FiltersBar.vue'
import ListPagination from '../components/ListPagination.vue'

type View = 'operators' | 'strategies'
type Sort = 'count' | 'win' | 'name'

/** 表格的一行：干员和策略共用同一张表。 */
interface Row {
  key: string
  name: string
  hint?: string
  avatar?: string
  icon?: string
  count: number
  usage_rate: number
  wins: number
  losses: number
  win_rate: number
}

const { filters, revision } = logbook()
const route = useRoute()
const router = useRouter()
// 视图写进地址栏（?view=strategies），首页「完整策略列表」可以直接跳过来。
const view = computed<View>({
  get: () => route.query.view === 'strategies' ? 'strategies' : 'operators',
  set: value => { void router.replace({ query: { ...route.query, view: value === 'strategies' ? 'strategies' : undefined } }) },
})
const viewOptions: { label: string; value: View }[] = [{ label: '干员', value: 'operators' }, { label: '策略', value: 'strategies' }]
const noun = computed(() => view.value === 'strategies' ? '策略' : '干员')

const page = ref(1)
const pageSize = ref(10)
const sort = ref<Sort>('count')
const q = ref('')
const search = ref('')
const sortOptions = computed(() => [
  { label: '按出场局数', value: 'count' },
  { label: '按出场胜率', value: 'win' },
  { label: '按名称', value: 'name' },
])

watch(q, (value, _, onCleanup) => {
  const trimmed = value.trim()
  if (!trimmed) {
    search.value = ''
    return
  }
  const timer = window.setTimeout(() => { search.value = trimmed }, 220)
  onCleanup(() => window.clearTimeout(timer))
})
watch(view, () => { q.value = ''; search.value = ''; page.value = 1 })

// 干员：搜索与排序在后端；策略：记录里可能存 band id 或策略名，在前端统一解析后再搜索排序。
// 两份数据都预先加载，切换视图时表格不会先塌掉再撑开。
const operatorUrl = computed(() => '/operators' + query(filters, view.value === 'operators' ? { sort: sort.value, q: search.value } : {}))
const strategyUrl = computed(() => '/strategies' + query(filters))
const operatorData = useResource<{ with_squad: number; operators: Operator[] }>(operatorUrl, revision, true)
const strategyData = useResource<{ matches: number; with_strategy: number; strategies: StrategyStat[] }>(strategyUrl, revision, true)
const active = computed(() => view.value === 'strategies' ? strategyData : operatorData)
const pending = computed(() => active.value.pending.value)
const error = computed(() => active.value.error.value)
const loaded = computed(() => Boolean(view.value === 'strategies' ? strategyData.data.value : operatorData.data.value))

const rows = computed<Row[]>(() => {
  if (view.value === 'operators') {
    return (operatorData.data.value?.operators ?? []).map(row => ({ ...row, key: row.id, avatar: portrait(row.id) }))
  }
  const term = search.value.toLowerCase()
  const list = (strategyData.data.value?.strategies ?? []).map(row => ({
    ...row, key: row.name, name: strategyOf(row.name), hint: unitOf(row.name) || undefined, icon: strategyIcon(row.name),
  })).filter(row => !term || row.name.toLowerCase().includes(term) || (row.hint ?? '').toLowerCase().includes(term))
  const keys: Record<Sort, (a: Row, b: Row) => number> = {
    count: (a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-CN'),
    win: (a, b) => b.win_rate - a.win_rate || b.count - a.count || a.name.localeCompare(b.name, 'zh-CN'),
    name: (a, b) => a.name.localeCompare(b.name, 'zh-CN'),
  }
  return list.sort(keys[sort.value])
})
const summary = computed(() => {
  if (view.value === 'operators') {
    const data = operatorData.data.value
    return data ? `${data.with_squad} 局有阵容明细${rows.value.length ? `，共 ${rows.value.length} 名干员` : ''}` : ''
  }
  const data = strategyData.data.value
  return data ? `${data.with_strategy} 局有策略记录${rows.value.length ? `，共 ${rows.value.length} 种策略` : ''}` : ''
})

const pageCount = computed(() => Math.ceil(rows.value.length / pageSize.value))
const currentPage = computed(() => Math.min(page.value, Math.max(1, pageCount.value)))
const displayed = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return rows.value.slice(start, start + pageSize.value)
})

function changePageSize(size: number) {
  pageSize.value = size
  page.value = 1
}

watch([() => active.value.resolvedUrl.value, search, sort], () => { page.value = 1 }, { flush: 'sync' })
watch(pageCount, () => { page.value = currentPage.value })
</script>

<template>
  <FiltersBar />

  <section class="panel table-panel" aria-labelledby="operator-title">
    <div class="table-heading operator-toolbar">
      <div>
        <div class="ranking-title">
          <h2 id="operator-title">出场榜</h2>
          <NRadioGroup v-model:value="view" size="small" name="ranking-view" aria-label="统计对象">
            <NRadioButton v-for="option in viewOptions" :key="option.value" :value="option.value" :label="option.label" />
          </NRadioGroup>
        </div>
        <p class="muted" role="status">
          <template v-if="pending && !loaded">正在读取{{ noun }}数据…</template>
          <template v-else>{{ summary }}</template>
        </p>
      </div>
      <div class="operator-options">
        <NInput v-model:value="q" clearable size="small" :placeholder="`搜索${noun}名称`" :aria-label="`搜索${noun}名称`" />
        <NSelect v-model:value="sort" size="small" :options="sortOptions" aria-label="排序" />
      </div>
    </div>
    <p v-if="error" class="table-feedback load-message" role="alert">
      {{ error }} <span v-if="loaded">正在显示上次成功的结果。</span> <button type="button" @click="active.refresh">重试</button>
    </p>
    <div v-if="loaded" class="scroll" :aria-busy="pending">
      <table class="operator-table">
        <colgroup>
          <col class="operator-name-col">
          <col class="operator-usage-col" span="2">
          <col class="operator-result-col" span="2">
          <col>
        </colgroup>
        <thead>
          <tr>
            <th scope="col">{{ noun }}</th>
            <th scope="col">出场<wbr>局数</th>
            <th scope="col">出场率</th>
            <th scope="col">胜</th>
            <th scope="col">负</th>
            <th scope="col">出场<wbr>胜率</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayed" :key="row.key">
            <th scope="row">
              <span class="with-avatar" :title="row.hint">
                <AvatarImage v-if="row.avatar" :src="row.avatar" :name="row.name" />
                <img v-else-if="row.icon" class="strategy-icon ranking-strategy-icon" :src="row.icon" alt="">
                <span>{{ row.name }}<small v-if="row.hint" class="ranking-hint">{{ row.hint }}</small></span>
              </span>
            </th>
            <td>{{ row.count }}</td>
            <td>{{ percent(row.usage_rate) }}</td>
            <td class="operator-wins">{{ row.wins }}</td>
            <td class="operator-losses">{{ row.losses }}</td>
            <td>
              <span class="operator-win-rate">
                <span>{{ percent(row.win_rate) }}</span>
                <span class="operator-win-bar" aria-hidden="true"><i :style="{ width: row.win_rate * 100 + '%' }"></i></span>
              </span>
            </td>
          </tr>
          <tr v-if="!pending && !error && !rows.length">
            <td class="empty-cell" colspan="6">
              {{ search ? `没有找到匹配的${noun}。` : view === 'strategies' ? '当前筛选范围内没有策略记录。' : '当前筛选范围内没有阵容明细。' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ListPagination v-if="rows.length" :page="currentPage" :page-size="pageSize" :total="rows.length"
      :disabled="pending" @update:page="page = $event" @update:page-size="changePageSize" />
  </section>
</template>

<style scoped>
.ranking-title { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
.ranking-title + .muted { margin-top: .55rem; }
.ranking-strategy-icon { width: 30px; height: 30px; }
.ranking-hint { display: block; color: var(--muted); font-size: .75rem; font-weight: 400; }
</style>
