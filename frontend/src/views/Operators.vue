<script setup lang="ts">
import { computed, ref } from 'vue'
import { logbook } from '../context'
import { query, rolePath, useResource } from '../api'
import { percent } from '../format'
import type { Operator } from '../models'
import Feedback from '../components/Feedback.vue'
import FiltersBar from '../components/FiltersBar.vue'

const { role, filters, revision } = logbook()
const sorts = [
  { value: 'count', label: '按出场局数' },
  { value: 'win', label: '按胜率' },
  { value: 'name', label: '按名称' },
] as const
const sort = ref<'count' | 'win' | 'name'>('count')
const q = ref('')

const url = rolePath(role, () => '/operators' + query(filters, { sort: sort.value, q: q.value }))
const { data, pending, error, refresh } = useResource<{ with_squad: number; operators: Operator[] }>(url, revision)

const rows = computed<Operator[]>(() => data.value?.operators ?? [])
const topUsage = computed(() => rows.value.reduce((max, row) => Math.max(max, row.count), 0) || 1)
const topRate = computed(() => rows.value.reduce((max, row) => Math.max(max, row.win_rate), 0) || 1)
</script>

<template>
  <FiltersBar />
  <div class="toolbar">
    <label class="filter-field">搜索干员
      <input v-model="q" type="search" maxlength="100" placeholder="输入名称" aria-label="按名称搜索干员">
    </label>
    <label class="filter-field">排序
      <span class="select-field">
        <select v-model="sort" aria-label="排序方式">
          <option v-for="item in sorts" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </span>
    </label>
  </div>

  <Feedback v-if="pending" pending />
  <Feedback v-else-if="error" :error="error" @retry="refresh" />
  <template v-else-if="rows.length">
    <p class="muted">{{ data?.with_squad }} 局有阵容明细，共 {{ rows.length }} 名干员出场。</p>
    <div class="table-wrap">
      <table>
        <caption class="visually-hidden">干员出场与胜率统计</caption>
        <thead>
          <tr>
            <th scope="col">干员</th>
            <th scope="col">出场</th>
            <th scope="col">出场率</th>
            <th scope="col">胜</th>
            <th scope="col">负</th>
            <th scope="col">胜率</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td class="name-cell">{{ row.name }}</td>
            <td>{{ row.count }}</td>
            <td>
              <div class="bar" :title="percent(row.usage_rate)"><span :style="{ width: (row.count / topUsage) * 100 + '%' }"></span></div>
            </td>
            <td>{{ row.wins }}</td>
            <td>{{ row.losses }}</td>
            <td>
              <div class="bar" :title="percent(row.win_rate)">
                <span :style="{ width: (row.win_rate / topRate) * 100 + '%' }"></span>
              </div>
              <small class="muted">{{ percent(row.win_rate) }}</small>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </template>
  <Feedback v-else empty="当前范围内没有阵容明细。可调整筛选，或导入含阵容的战绩文件。">
    <RouterLink class="button-link" to="/archive">前往档案管理</RouterLink>
  </Feedback>
</template>
