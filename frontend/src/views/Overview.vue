<script setup lang="ts">
import { computed, reactive, ref, type Component } from 'vue'
import { NIcon } from 'naive-ui'
import { FlameOutline, LayersOutline, NuclearOutline, ShieldOutline, SkullOutline, SpeedometerOutline } from '@vicons/ionicons5'
import { logbook } from '../context'
import { query, useResource } from '../api'
import { BOND_ICONS, DIFFICULTY_ICONS } from '../assets'
import { number, peakText, percent, pickMajorBond, resultLabel } from '../format'
import { portrait } from '../icons'
import type { DistributionGroup, Overview, Scope } from '../models'
import FiltersBar from '../components/FiltersBar.vue'
import TrendChart from '../components/TrendChart.vue'
import type { Metric } from '../components/TrendChart.vue'

const { filters, revision } = logbook()
const scope = ref<Scope>('recent')
const missingPortraits = reactive(new Set<string>())
const url = computed(() => '/overview' + query(filters, { scope: scope.value }))
const { data, pending, error, resolvedUrl, refresh } = useResource<Overview>(url, revision, true)
const renderedScope = computed(() => (new URLSearchParams(resolvedUrl.value?.split('?')[1]).get('scope') as Scope | null) ?? 'recent')

const rate = computed(() => data.value?.matches ? data.value.wins / data.value.matches : 0)
const charts: { metric: Metric; match: string; day: string }[] = [
  { metric: 'layers', match: '盟约总层数', day: '单日最高盟约总层数' },
  { metric: 'peak', match: '单项最高盟约层数', day: '单项最高盟约层数' },
  { metric: 'coins', match: '金币花费', day: '单日金币总花费' },
  { metric: 'kills', match: '敌人击杀', day: '场均击杀' },
  { metric: 'rounds', match: '通过回合', day: '场均回合' },
]
const period = computed(() => data.value?.start ? `${data.value.start} — ${data.value.end}` : '当前筛选无对局')
const majorBond = computed(() => (data.value?.peak ? pickMajorBond(data.value.peak.names) : ''))
const distributionUrl = computed(() => '/distribution' + query(filters))
const distribution = useResource<DistributionGroup[]>(distributionUrl, revision, true)

const TIERS: Record<string, { icon: Component; color: string }> = {
  标准模拟: { icon: ShieldOutline, color: '#e0b04a' },
  险境模拟: { icon: FlameOutline, color: '#e58b48' },
  绝境模拟: { icon: SkullOutline, color: '#e0533f' },
  终极模拟: { icon: NuclearOutline, color: '#d02f45' },
  极速模拟: { icon: SpeedometerOutline, color: '#7fae6a' },
}
function tierOf(label: string): { icon: Component; color: string } {
  if (TIERS[label]) return TIERS[label]
  if (label.startsWith('规程等级')) return { icon: LayersOutline, color: '#d8b24a' }
  return { icon: LayersOutline, color: 'var(--muted)' }
}
function maxTotal(groups: DistributionGroup[] | null) {
  return Math.max(1, ...(groups ?? []).flatMap(group => group.buckets.map(bucket => bucket.total)))
}
const topTotal = computed(() => maxTotal(distribution.data.value))
</script>

<template>
  <FiltersBar />
  <p v-if="pending && !data" class="load-message" role="status">正在读取战绩…</p>
  <p v-if="error" class="load-message" role="alert">
    {{ error }} <button type="button" @click="refresh">重试</button>
  </p>

  <template v-if="data">
    <div class="summary-grid">
      <section class="performance panel" aria-labelledby="performance-title">
        <div class="split">
          <h2 id="performance-title">作战表现</h2>
          <span class="period">{{ period }}</span>
        </div>
        <div class="performance-row">
          <div class="win-rate">
            <strong>{{ data.matches ? percent(rate) : '—' }}</strong><span>胜率</span>
          </div>
          <div>
            <p class="summary-text">
              {{ data.matches }} 局　·　{{ data.wins }} 胜　/　{{ data.matches - data.wins }} 负<template v-if="data.excluded"> · 已排除 {{ data.excluded }} 局</template>
            </p>
            <div class="meter" aria-hidden="true"><i :style="{ width: (data.matches ? rate * 100 : 0) + '%' }"></i></div>
          </div>
        </div>
        <div class="recent">
          <h3>最近十局</h3>
          <div class="streak">
            <span v-for="(result, index) in data.recent_results" :key="index" class="chip" :class="{ loss: result === 'loss' }">{{ resultLabel(result) }}</span>
          </div>
        </div>
      </section>

      <section class="stat-panel panel" aria-labelledby="stats-title">
        <h2 id="stats-title">盟约与资金</h2>
        <dl class="stats">
          <div><dt>单局最高总层数</dt><dd>{{ data.max_layers === null ? '—' : number(data.max_layers) + ' 层' }}</dd></div>
          <div>
            <dt>单项最高盟约</dt>
            <dd id="peak" class="peak-value" :title="data.peak ? data.peak.names.join('、') : ''">
              <template v-if="data.peak">
                <img v-if="BOND_ICONS[majorBond]" :src="BOND_ICONS[majorBond]" width="22" height="22" alt="">
                <span class="bond-glyph" v-else aria-hidden="true"></span>
                <b>{{ number(data.peak.layers) }} 层</b>
              </template>
              <template v-else>—</template>
            </dd>
          </div>
          <div><dt>金币总花费</dt><dd>{{ number(data.total_coins) }}</dd></div>
          <div><dt>场均金币</dt><dd>{{ number(data.average_coins) }}</dd></div>
        </dl>
      </section>
    </div>

    <section v-if="distribution.error.value || distribution.data.value?.some(group => group.buckets.some(bucket => bucket.total))"
      class="content-section" aria-labelledby="distribution-title">
      <div class="split section-heading">
        <h2 id="distribution-title">模式分布</h2>
        <span class="muted">按难度分档统计胜负</span>
      </div>
      <p v-if="distribution.error.value" class="load-message" role="alert">
        {{ distribution.error.value }} <button type="button" @click="distribution.refresh">重试</button>
      </p>
      <div v-if="distribution.data.value?.length" class="distribution panel" :aria-busy="distribution.pending.value">
        <section v-for="group in distribution.data.value" :key="group.play" class="dist-group">
          <h3>{{ group.play }}</h3>
          <div v-for="bucket in group.buckets" :key="bucket.label" class="dist-row" :class="{ zero: !bucket.total }">
            <span class="dist-icon" :style="{ color: tierOf(bucket.label).color }">
              <img v-if="DIFFICULTY_ICONS[bucket.label]" :src="DIFFICULTY_ICONS[bucket.label]" width="18" height="18" alt="">
              <NIcon v-else :component="tierOf(bucket.label).icon" />
            </span>
            <span class="dist-label">{{ bucket.label }}</span>
            <span class="dist-count win">胜 {{ bucket.wins }}</span>
            <span class="dist-count loss">负 {{ bucket.losses }}</span>
            <span class="dist-total">总 {{ bucket.total }} 场</span>
            <span class="dist-bar">
              <i :style="{ width: (bucket.total / topTotal) * 100 + '%', background: tierOf(bucket.label).color }"></i>
            </span>
          </div>
        </section>
      </div>
    </section>

    <section class="content-section" aria-labelledby="trend-title">
      <div class="split section-heading">
        <h2 id="trend-title">对局趋势</h2>
        <div class="chart-controls">
          <span v-if="pending" class="muted" role="status">正在更新…</span>
          <div v-show="renderedScope !== 'day' && data.points.length" class="chart-legend" aria-label="图例">
            <span class="win-key">● 胜</span><span class="loss-key">◆ 负</span>
          </div>
          <span class="select-field">
            <select v-model="scope" aria-label="统计粒度">
              <option value="recent">近 10 场</option>
              <option value="all">全部对局</option>
              <option value="day">按日期</option>
            </select>
          </span>
        </div>
      </div>
      <div v-if="data.points.length" class="trend-grid" :aria-busy="pending">
        <TrendChart v-for="chart in charts" :key="chart.metric" :points="data.points" :metric="chart.metric"
          :scope="renderedScope" :title="renderedScope === 'day' ? chart.day : chart.match" />
        <TrendChart v-if="renderedScope === 'day'" :points="data.points" metric="average" :scope="renderedScope" title="场均金币" />
      </div>
      <p v-else class="empty-state">当前筛选无对局趋势。</p>
    </section>

    <section class="content-section" aria-labelledby="operators-title">
      <div class="split section-heading">
        <div>
          <h2 id="operators-title">常用干员</h2>
          <p class="muted">{{ data.with_squad }} 局有阵容明细</p>
        </div>
        <RouterLink class="button-link" to="/operators">完整干员列表</RouterLink>
      </div>
      <div v-if="data.operators.length" class="roster">
        <article v-for="operator in data.operators" :key="operator.id" class="op">
          <img v-if="!missingPortraits.has(operator.id)" :src="portrait(operator.id)" alt="" @error="missingPortraits.add(operator.id)">
          <span v-else class="op-fallback" aria-hidden="true">{{ operator.name.slice(0, 1) }}</span>
          <div>
            <b>{{ operator.name }}</b>
            <small>出场 {{ operator.count }} 局</small>
          </div>
        </article>
      </div>
      <p v-else class="muted">暂无阵容明细</p>
    </section>

    <section class="content-section" aria-labelledby="bonds-title">
      <div class="split section-heading">
        <h2 id="bonds-title">常用盟约</h2>
        <span class="muted">按出场局数排序</span>
      </div>
      <div v-if="data.bonds.length" class="bond-usage">
        <article v-for="bond in data.bonds" :key="bond.name" class="usage-card">
          <img v-if="BOND_ICONS[bond.name]" :src="BOND_ICONS[bond.name]" width="36" height="36" alt="">
          <span v-else class="bond-glyph" aria-hidden="true"></span>
          <div>
            <b>{{ bond.name }}</b>
            <small>{{ bond.count }} 局 · 场均 {{ number(bond.average) }} 层</small>
          </div>
        </article>
      </div>
      <p v-else class="muted">当前筛选无盟约记录</p>
    </section>
  </template>
</template>
