<script setup lang="ts">
import { ref } from 'vue'
import { NInput, NSelect } from 'naive-ui'
import { logbook } from '../context'
import { computed } from 'vue'
import { query, useResource } from '../api'
import { percent } from '../format'
import { portrait } from '../icons'
import type { Operator } from '../models'
import FiltersBar from '../components/FiltersBar.vue'

const { filters, revision } = logbook()
const sort = ref<'count' | 'win' | 'name'>('count')
const q = ref('')
const sortOptions = [
  { label: '按出场局数', value: 'count' },
  { label: '按出场胜率', value: 'win' },
  { label: '按名称', value: 'name' },
]

const url = computed(() => '/operators' + query(filters, { sort: sort.value, q: q.value }))
const { data, pending, error, refresh } = useResource<{ with_squad: number; operators: Operator[] }>(url, revision)
</script>

<template>
  <FiltersBar />

  <p v-if="pending" class="load-message" role="status">正在读取干员数据…</p>
  <p v-else-if="error" class="load-message" role="alert">
    {{ error }} <button type="button" @click="refresh">重试</button>
  </p>

  <section v-else class="panel table-panel" aria-labelledby="operator-title">
    <div class="table-heading operator-toolbar">
      <div>
        <h2 id="operator-title">出场榜</h2>
        <p class="muted" role="status">
          {{ data?.with_squad ?? 0 }} 局有阵容明细<template v-if="data?.operators.length">，共 {{ data.operators.length }} 名干员</template>
        </p>
      </div>
      <div class="operator-options">
        <NInput v-model:value="q" clearable size="small" placeholder="搜索干员名称" aria-label="搜索干员名称" />
        <NSelect v-model:value="sort" size="small" :options="sortOptions" aria-label="排序" />
      </div>
    </div>
    <div class="scroll">
      <table class="operator-table">
        <thead>
          <tr>
            <th scope="col">干员</th>
            <th scope="col">出场局数</th>
            <th scope="col">出场率</th>
            <th scope="col">胜</th>
            <th scope="col">负</th>
            <th scope="col">出场胜率</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data?.operators ?? []" :key="row.id">
            <td><img :src="portrait(row.id)" width="37" height="37" alt="" @error="($event.target as HTMLImageElement).style.display = 'none'">{{ row.name }}</td>
            <td>{{ row.count }}</td>
            <td>{{ percent(row.usage_rate) }}</td>
            <td>{{ row.wins }}</td>
            <td>{{ row.losses }}</td>
            <td>{{ percent(row.win_rate) }}</td>
          </tr>
          <tr v-if="!data?.operators.length">
            <td class="empty-cell" colspan="6">当前筛选范围内没有阵容明细。</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
