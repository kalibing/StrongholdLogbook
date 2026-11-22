<script setup lang="ts">
import { computed, ref } from 'vue'
import { logbook } from '../context'
import { query, rolePath, useResource } from '../api'
import { number, peakText, percent, resultLabel } from '../format'
import type { Overview, Scope } from '../models'
import Feedback from '../components/Feedback.vue'
import FiltersBar from '../components/FiltersBar.vue'
import TrendChart from '../components/TrendChart.vue'

const { role, filters, revision } = logbook()
const scope = ref<Scope>('recent')
const { data, pending, error, refresh } = useResource<Overview>(rolePath(role, () =>
  '/overview' + query(filters, { scope: scope.value })), revision)
const rate = computed(() => data.value?.matches ? data.value.wins / data.value.matches : null)
const charts = [
  { metric: 'layers', title: '盟约总层数', day: '单日最高盟约总层数' },
  { metric: 'peak', title: '单项最高盟约层数' },
  { metric: 'coins', title: '金币花费', day: '单日金币总花费' },
  { metric: 'kills', title: '敌人击杀', day: '场均击杀' },
  { metric: 'rounds', title: '通过回合', day: '场均回合' },
] as const
</script>

<template>
  <FiltersBar />
  <Feedback v-if="pending || error" :pending="pending" :error="error" @retry="refresh" />
  <template v-else-if="data?.matches">
    <div class="summary-grid">
      <section class="performance panel" aria-labelledby="performance-title">
        <div class="split"><h2 id="performance-title">作战表现</h2><span class="period">{{ data.start }} — {{ data.end }}</span></div>
        <div class="performance-row">
          <div class="win-rate"><strong>{{ rate === null ? '—' : percent(rate) }}</strong><span>胜率</span></div>
          <div>
            <p class="summary-text">{{ data.matches }} 局 · {{ data.wins }} 胜 / {{ data.matches - data.wins }} 负<span v-if="data.excluded"> · 已排除 {{ data.excluded }} 局</span></p>
            <progress class="meter" :value="data.wins" :max="data.matches" aria-label="胜场占比" />
          </div>
        </div>
        <div class="recent"><h3>最近十局</h3><div class="streak"><span v-for="(result, index) in data.recent_results" :key="index" class="chip" :class="{ loss: result === 'loss' }">{{ resultLabel(result) }}</span></div></div>
      </section>
      <section class="stat-panel panel" aria-labelledby="stats-title">
        <h2 id="stats-title">盟约与资金</h2>
        <dl class="stats">
          <div><dt>单局最高总层数</dt><dd>{{ data.max_layers === null ? '—' : number(data.max_layers) + ' 层' }}</dd></div>
          <div><dt>单项最高盟约</dt><dd class="peak-value">{{ peakText(data.peak) }}</dd></div>
          <div><dt>金币总花费</dt><dd>{{ number(data.total_coins) }}</dd></div>
          <div><dt>场均金币</dt><dd>{{ number(data.average_coins) }}</dd></div>
        </dl>
      </section>
    </div>
    <section class="content-section" aria-labelledby="trend-title">
      <div class="split section-heading">
        <h2 id="trend-title">对局趋势</h2>
        <div class="chart-controls">
          <div v-if="scope !== 'day'" class="chart-legend"><span class="win-key">● 胜</span><span class="loss-key">◆ 负</span></div>
          <span class="select-field"><select v-model="scope" aria-label="统计粒度"><option value="recent">近 10 局</option><option value="all">全部对局</option><option value="day">按日期</option></select></span>
        </div>
      </div>
      <div class="trend-grid">
        <TrendChart v-for="chart in charts" :key="chart.metric" :points="data.points" :metric="chart.metric"
          :scope="scope" :title="scope === 'day' && 'day' in chart ? chart.day : chart.title" />
        <TrendChart v-if="scope === 'day'" :points="data.points" metric="average_coins" :scope="scope" title="场均金币" />
      </div>
    </section>
    <section class="content-section" aria-labelledby="operator-title">
      <div class="split section-heading">
        <div><h2 id="operator-title">常用干员</h2><p class="muted">{{ data.with_squad }} 局有阵容明细</p></div>
        <RouterLink class="button-link" to="/operators">完整干员列表</RouterLink>
      </div>
      <div v-if="data.operators.length" class="roster">
        <article v-for="operator in data.operators" :key="operator.id" class="usage-card">
          <div><strong>{{ operator.name }}</strong><small>出场 {{ operator.count }} 局 · {{ percent(operator.usage_rate) }}</small></div>
        </article>
      </div>
      <p v-else class="muted">暂无阵容明细</p>
    </section>
    <section class="content-section" aria-labelledby="bond-title">
      <div class="split section-heading"><h2 id="bond-title">常用盟约</h2><span class="muted">按出场局数排序</span></div>
      <div v-if="data.bonds.length" class="bond-usage">
        <article v-for="bond in data.bonds" :key="bond.name" class="usage-card">
          <div><strong>{{ bond.name }}</strong><small>{{ bond.count }} 局 · 场均 {{ number(bond.average) }} 层</small></div>
        </article>
      </div>
      <p v-else class="muted">暂无盟约记录</p>
    </section>
  </template>
  <Feedback v-else empty="当前范围内没有对局。可调整筛选，或导入一份战绩文件。">
    <RouterLink class="button-link" to="/archive">前往档案管理</RouterLink>
  </Feedback>
</template>
