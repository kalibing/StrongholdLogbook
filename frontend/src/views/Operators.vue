<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NInput, NSelect } from 'naive-ui'
import { logbook } from '../context'
import { query, useResource } from '../api'
import { percent } from '../format'
import { portrait } from '../icons'
import type { Operator } from '../models'
import AvatarImage from '../components/AvatarImage.vue'
import FiltersBar from '../components/FiltersBar.vue'

const { filters, revision } = logbook()
const sort = ref<'count' | 'win' | 'name'>('count')
const q = ref('')
const search = ref('')
const sortOptions = [
  { label: '按出场局数', value: 'count' },
  { label: '按出场胜率', value: 'win' },
  { label: '按名称', value: 'name' },
]

watch(q, (value, _, onCleanup) => {
  const trimmed = value.trim()
  if (!trimmed) {
    search.value = ''
    return
  }
  const timer = window.setTimeout(() => { search.value = trimmed }, 220)
  onCleanup(() => window.clearTimeout(timer))
})

const url = computed(() => '/operators' + query(filters, { sort: sort.value, q: search.value }))
const { data, pending, error, refresh } = useResource<{ with_squad: number; operators: Operator[] }>(url, revision, true)
</script>

<template>
  <FiltersBar />

  <section class="panel table-panel" aria-labelledby="operator-title">
    <div class="table-heading operator-toolbar">
      <div>
        <h2 id="operator-title">出场榜</h2>
        <p class="muted" role="status">
          <template v-if="pending">正在读取干员数据…</template>
          <template v-else-if="data">{{ data.with_squad }} 局有阵容明细<template v-if="data.operators.length">，共 {{ data.operators.length }} 名干员</template></template>
        </p>
      </div>
      <div class="operator-options">
        <NInput v-model:value="q" clearable size="small" placeholder="搜索干员名称" aria-label="搜索干员名称" />
        <NSelect v-model:value="sort" size="small" :options="sortOptions" aria-label="排序" />
      </div>
    </div>
    <p v-if="error" class="table-feedback load-message" role="alert">
      {{ error }} <span v-if="data">正在显示上次成功的结果。</span> <button type="button" @click="refresh">重试</button>
    </p>
    <div v-if="data" class="scroll" :aria-busy="pending">
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
            <td><span class="with-avatar"><AvatarImage :src="portrait(row.id)" :name="row.name" />{{ row.name }}</span></td>
            <td>{{ row.count }}</td>
            <td>{{ percent(row.usage_rate) }}</td>
            <td>{{ row.wins }}</td>
            <td>{{ row.losses }}</td>
            <td>{{ percent(row.win_rate) }}</td>
          </tr>
          <tr v-if="!pending && !error && !data.operators.length">
            <td class="empty-cell" colspan="6">{{ search ? '没有找到匹配的干员。' : '当前筛选范围内没有阵容明细。' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
