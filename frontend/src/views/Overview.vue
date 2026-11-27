<script setup lang="ts">
import { computed, reactive, ref, type Component } from 'vue'
import { NIcon, NSelect } from 'naive-ui'
import { FlameOutline, LayersOutline, NuclearOutline, PeopleOutline, ShieldOutline, SkullOutline, SpeedometerOutline, TrendingUpOutline } from '@vicons/ionicons5'
import { logbook } from '../context'
import { query, useResource } from '../api'
import { BOND_ICONS, BOSS_MARKS, DIFFICULTY_ICONS, FUNDS_ICON } from '../assets'
import { number, percent, pickMajorBond, resultLabel } from '../format'
import { portrait } from '../icons'
import type { DistributionGroup, MatchDetail, Overview } from '../models'
import FiltersBar from '../components/FiltersBar.vue'
import BondShareChart from '../components/BondShareChart.vue'
import MatchReport from '../components/MatchReport.vue'
import TrendChart from '../components/TrendChart.vue'
import TrophyIcon from '../components/TrophyIcon.vue'
import type { Metric } from '../components/TrendChart.vue'

const { filters, revision } = logbook()
const sections = [
  { id: 'summary', label: '作战概况', icon: ShieldOutline },
  { id: 'bonds', label: '盟约分析', icon: LayersOutline },
  { id: 'trend', label: '对局趋势', icon: TrendingUpOutline },
  { id: 'operators', label: '常用干员', icon: PeopleOutline },
] as const
const section = ref<(typeof sections)[number]['id']>('summary')
const scope = ref<'recent' | 'all'>('recent')
const scopeOptions = [{ label: '近 10 场', value: 'recent' }, { label: '全部对局', value: 'all' }]
const detailUrl = ref<string | null>(null)
const missingPortraits = reactive(new Set<string>())
const url = computed(() => '/overview' + query(filters, { scope: scope.value }))
const { data, pending, error, refresh } = useResource<Overview>(url, revision, true)
const report = useResource<MatchDetail>(detailUrl, revision)

const rate = computed(() => data.value?.matches ? data.value.wins / data.value.matches : 0)
const charts: { metric: Metric; title: string }[] = [
  { metric: 'peak', title: '单项最高盟约层数' },
  { metric: 'layers', title: '盟约总层数' },
  { metric: 'coins', title: '金币花费' },
  { metric: 'kills', title: '敌人击杀' },
  { metric: 'rounds', title: '通过回合' },
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
  return TIERS[label] ?? { icon: LayersOutline, color: 'var(--muted)' }
}
function tierIcon(label: string): string {
  return DIFFICULTY_ICONS[label] ?? ''
}
function openMatch(id: string) {
  detailUrl.value = '/matches/' + id
}
</script>

<template>
  <FiltersBar />
  <p v-if="pending && !data" class="load-message" role="status">正在读取战绩…</p>
  <p v-if="error" class="load-message" role="alert">
    {{ error }} <span v-if="data">正在显示上次成功的结果。</span> <button type="button" @click="refresh">重试</button>
  </p>

  <template v-if="data">
    <fieldset class="overview-cards" aria-label="战绩总览分段">
      <label v-for="option in sections" :key="option.id">
        <input v-model="section" type="radio" name="overview-section" :value="option.id">
        <span class="overview-card">
          <NIcon :component="option.icon" size="19" aria-hidden="true" />
          {{ option.label }}
        </span>
      </label>
    </fieldset>

    <Transition name="overview-panel">
      <div v-if="section === 'summary'">
        <div class="summary-grid">
          <section class="performance panel" aria-labelledby="performance-title">
            <div class="split">
              <h2 id="performance-title">作战表现</h2>
              <span class="period">{{ period }}</span>
            </div>
            <div class="performance-row">
              <div class="win-rate">
                <span>胜率</span>
                <strong>{{ data.matches ? percent(rate) : '—' }}</strong>
                <div class="meter" aria-hidden="true"><i :style="{ width: (data.matches ? rate * 100 : 0) + '%' }"></i></div>
              </div>
              <dl class="match-totals">
                <div><dt>总局数</dt><dd>{{ number(data.matches) }}</dd></div>
                <div class="win"><dt>胜场</dt><dd>{{ number(data.wins) }}</dd></div>
                <div class="loss"><dt>负场</dt><dd>{{ number(data.matches - data.wins) }}</dd></div>
              </dl>
            </div>
            <div class="recent">
              <h3>最近十局</h3>
              <div class="streak">
                <span v-for="(result, index) in data.recent_results" :key="index" class="chip" :class="{ loss: result === 'loss' }">{{ resultLabel(result) }}</span>
              </div>
              <small v-if="data.excluded" class="excluded-count">已排除 {{ number(data.excluded) }} 局</small>
            </div>
            <dl class="overview-trophies" title="汇总当前筛选内有奖杯记录的对局">
              <div>
                <dt><TrophyIcon :badge="data.trophy_badge" :size="38" />奖杯数</dt>
                <dd class="trophy-change-value" :class="{ 'trophy-change-value--loss': (data.trophy_change ?? 0) < 0 }">
                  {{ number(data.trophy_change ?? null) }}
                </dd>
              </div>
            </dl>
          </section>

          <section class="stat-panel panel" aria-labelledby="stats-title">
            <h2 id="stats-title">盟约与资金</h2>
            <dl class="stats">
              <div><dt>单局最高总层数</dt><dd>{{ data.max_layers === null ? '—' : number(data.max_layers) + ' 层' }}</dd></div>
              <div>
                <dt>单项最高盟约</dt>
                <dd id="peak" class="peak-value" :title="data.peak ? data.peak.names.join('、') : ''">
                  <template v-if="data.peak">
                    <img v-if="BOND_ICONS[majorBond]" :src="BOND_ICONS[majorBond]" width="40" height="40" :alt="majorBond">
                    <span class="bond-glyph" v-else aria-hidden="true"></span>
                    <b>{{ number(data.peak.layers) }} 层</b>
                  </template>
                  <template v-else>—</template>
                </dd>
              </div>
              <div>
                <dt>金币总花费</dt>
                <dd class="funds-value">
                  <img v-if="data.total_coins !== null" :src="FUNDS_ICON" width="26" height="22" alt="">
                  <span>{{ number(data.total_coins) }}</span>
                </dd>
              </div>
              <div><dt>场均金币</dt><dd>{{ number(data.average_coins) }}</dd></div>
            </dl>
          </section>
        </div>

        <section v-if="distribution.error.value || distribution.data.value?.some(group => group.buckets.some(bucket => bucket.total))"
          class="content-section" aria-labelledby="distribution-title">
          <div class="split section-heading">
            <h2 id="distribution-title">模式分布</h2>
            <p id="distribution-note" class="muted">首领击破按局计，同一局可计入普通和隐藏两列。</p>
          </div>
          <p v-if="distribution.error.value" class="load-message" role="alert">
            {{ distribution.error.value }} <button type="button" @click="distribution.refresh">重试</button>
          </p>
          <div v-if="distribution.data.value?.length" class="distribution panel" :aria-busy="distribution.pending.value">
            <table class="dist-table" aria-labelledby="distribution-title" aria-describedby="distribution-note">
              <thead>
                <tr>
                  <th scope="col">难度 / 等级</th>
                  <th scope="col">总局数</th>
                  <th scope="col">胜</th>
                  <th scope="col">负</th>
                  <th scope="col">胜率</th>
                  <th scope="col" title="击破至少一个普通首领的场次">
                    <span class="dist-boss-heading dist-boss-heading--normal">
                      <img :src="BOSS_MARKS.normal" width="23" height="21" alt="">
                      <span>普通<wbr>击破</span>
                    </span>
                  </th>
                  <th scope="col" title="击破至少一个隐藏首领的场次">
                    <span class="dist-boss-heading dist-boss-heading--hidden">
                      <img :src="BOSS_MARKS.hidden" width="23" height="21" alt="">
                      <span>隐藏<wbr>击破</span>
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody v-for="group in distribution.data.value" :key="group.play" class="dist-group">
                <tr class="dist-group-heading"><th scope="rowgroup" colspan="7">{{ group.play }}</th></tr>
                <tr v-for="bucket in group.buckets" :key="bucket.label" class="dist-row">
                  <th scope="row">
                    <span class="dist-tier">
                      <span class="dist-icon" :style="{ color: tierOf(bucket.label).color }">
                        <img v-if="tierIcon(bucket.label)" :src="tierIcon(bucket.label)" width="18" height="18" alt="">
                        <NIcon v-else :component="tierOf(bucket.label).icon" />
                      </span>
                      <span>{{ bucket.label }}</span>
                    </span>
                  </th>
                  <td>{{ number(bucket.total) }}</td>
                  <td class="win">{{ number(bucket.wins) }}</td>
                  <td class="loss">{{ number(bucket.losses) }}</td>
                  <td>
                    <span class="dist-rate">
                      <span :key="bucket.total ? bucket.wins / bucket.total : 'empty'" class="dist-rate-value">
                        {{ bucket.total ? percent(bucket.wins / bucket.total) : '—' }}
                      </span>
                      <span class="dist-bar" aria-hidden="true">
                        <i :style="{ width: (bucket.total ? bucket.wins / bucket.total * 100 : 0) + '%' }"></i>
                      </span>
                    </span>
                  </td>
                  <td :class="{ 'dist-normal-count': bucket.normal_boss }">{{ number(bucket.normal_boss ?? null) }}</td>
                  <td :class="{ 'dist-hidden-count': bucket.hidden }">{{ number(bucket.hidden ?? null) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <div v-else-if="section === 'bonds'">
        <BondShareChart v-if="data.bond_layers" :bonds="data.bond_layers" description="当前筛选对局的累计层数占比"
          :aria-busy="pending" />
        <section class="content-section" aria-labelledby="bonds-title">
          <div class="split section-heading">
            <h2 id="bonds-title">常用盟约</h2>
            <span class="muted">按激活局数排序 · 仅对激活的对局取平均</span>
          </div>
          <div v-if="data.bonds.length" class="bond-usage">
            <article v-for="bond in data.bonds" :key="bond.name" class="usage-card">
              <div class="usage-heading">
                <img v-if="BOND_ICONS[bond.name]" :src="BOND_ICONS[bond.name]" width="36" height="36" alt="">
                <span v-else class="bond-glyph" aria-hidden="true"></span>
                <h3>{{ bond.name }}</h3>
              </div>
              <dl class="usage-stats">
                <div><dt>激活局数</dt><dd><strong>{{ number(bond.count) }}</strong><span>局</span></dd></div>
                <div><dt>场均层数</dt><dd><strong>{{ number(bond.average) }}</strong><span>层</span></dd></div>
              </dl>
            </article>
          </div>
          <p v-else class="muted">当前筛选无盟约记录</p>
        </section>
      </div>

      <section v-else-if="section === 'trend'" aria-labelledby="trend-title">
        <div class="split section-heading">
          <h2 id="trend-title">对局趋势</h2>
          <div class="chart-controls">
            <span v-if="pending" class="muted" role="status">正在更新…</span>
            <div v-show="data.points.length" class="chart-legend" aria-label="图例">
              <span class="win-key">■ 胜</span><span class="loss-key">■ 负</span>
            </div>
            <NSelect v-model:value="scope" class="trend-scope" size="small" :options="scopeOptions" aria-label="对局范围" />
          </div>
        </div>
        <div v-if="data.points.length" class="trend-grid" :aria-busy="pending">
          <TrendChart v-for="chart in charts" :key="chart.metric" :points="data.points" :metric="chart.metric"
            :title="chart.title" @open-match="openMatch" />
        </div>
        <p v-else class="empty-state">当前筛选无对局趋势。</p>
      </section>

      <section v-else-if="section === 'operators'" aria-labelledby="operators-title">
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
    </Transition>
  </template>

  <MatchReport v-if="detailUrl" :detail="report.data.value" :pending="report.pending.value"
    :error="report.error.value" @close="detailUrl = null" @retry="report.refresh" />
</template>

<style scoped>
.overview-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: .55rem;
  min-width: 0;
  margin: 1rem 0;
  padding: 0;
  border: 0;
}
.overview-cards label { position: relative; min-width: 0; cursor: pointer; }
.overview-cards input { position: absolute; width: 1px; height: 1px; clip-path: inset(50%); }
.overview-card {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: .5rem;
  min-height: 3rem;
  padding: .45rem;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--panel);
  color: var(--muted);
  font-weight: 650;
  text-align: center;
}
.overview-card :deep(.n-icon) { flex: none; }
.overview-cards label:hover .overview-card { border-color: var(--control-line); color: var(--text); }
.overview-cards input:checked + .overview-card {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, var(--panel));
  color: var(--accent);
}
.overview-cards input:focus-visible + .overview-card { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (prefers-reduced-motion: no-preference) {
  .overview-card {
    transition: background-color .16s ease, border-color .16s ease, color .16s ease, transform .16s ease;
  }
  .overview-cards label:hover .overview-card { transform: translateY(-1px); }
  .overview-cards label:active .overview-card { transform: scale(.98); }
  .overview-panel-enter-active {
    transition: opacity .2s ease-out, transform .2s cubic-bezier(.2, .7, .3, 1);
  }
  .overview-panel-enter-from { opacity: 0; transform: translateY(7px); }
}
@media (max-width: 540px) {
  .overview-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.trend-scope { width: 8rem; }
.overview-trophies {
  margin-top: .75rem; padding: .48rem .75rem; border: 1px solid var(--line); border-radius: 3px;
  background: var(--inset); color: var(--text); font-size: .92rem;
}
.overview-trophies > div { display: flex; align-items: center; justify-content: space-between; gap: .65rem; }
.overview-trophies dt { display: flex; align-items: center; gap: .65rem; font-weight: 650; }
.trophy-change-value { color: var(--accent); font: 700 clamp(1.5rem, 3vw, 2rem)/1 var(--numbers); }
.trophy-change-value--loss { color: var(--loss); }
</style>
