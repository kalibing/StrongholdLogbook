<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { NIcon } from 'naive-ui'
import { ChevronForwardOutline } from '@vicons/ionicons5'
import { query, useResource } from '../api'
import { BOND_ICONS, bossName } from '../assets'
import { strategyIcon, strategyOf } from '../bands'
import { logbook, newFilters } from '../context'
import { clockTime, difficultyLabel, number, percent, pickMajorBond, resultLabel } from '../format'
import type { DailyReview, MatchDetail, MatchPage, Overview } from '../models'
import MatchReport from '../components/MatchReport.vue'
import TierTag from '../components/TierTag.vue'
import ListPagination from '../components/ListPagination.vue'
import BondShareChart from '../components/BondShareChart.vue'
import BossLabel from '../components/BossLabel.vue'
import DailyReviewPanel from '../components/DailyReviewPanel.vue'
import TrophyIcon from '../components/TrophyIcon.vue'

const { revision } = logbook()
const HOUR = 60 * 60 * 1000
const CHINA_OFFSET = 8 * HOUR
const DAY = 24 * HOUR
const pageSize = ref(10)
const BOND_PREVIEW_LIMIT = 6

function yesterday(now = Date.now()) {
  return new Date(now + CHINA_OFFSET - DAY).toISOString().slice(0, 10)
}

const day = ref(yesterday())
const page = ref(1)
const detailUrl = ref<string | null>(null)
let midnightTimer: number | undefined

function updateDay() {
  window.clearTimeout(midnightTimer)
  const now = Date.now()
  day.value = yesterday(now)
  midnightTimer = window.setTimeout(updateDay, DAY - (now + CHINA_OFFSET) % DAY)
}

onMounted(() => {
  updateDay()
  window.addEventListener('focus', updateDay)
})
onBeforeUnmount(() => {
  window.clearTimeout(midnightTimer)
  window.removeEventListener('focus', updateDay)
})
watch(day, () => {
  page.value = 1
  detailUrl.value = null
}, { flush: 'sync' })

const filters = computed(() => ({ ...newFilters(), start: day.value, end: day.value }))
const overviewUrl = computed(() => '/overview' + query(filters.value, { scope: 'day' }))
const reviewUrl = computed(() => `/daily-review?day=${day.value}`)
const listPath = computed(() => '/matches' + query(filters.value, { include_breakdown: 'true' }))
const listUrl = computed(() => `${listPath.value}&page=${page.value}&limit=${pageSize.value}`)
const { data: overview, pending, error, refresh } = useResource<Overview>(overviewUrl, revision)
const list = useResource<MatchPage>(listUrl, revision, true)
const report = useResource<MatchDetail>(detailUrl, revision)
const { data: review, pending: reviewPending, error: reviewError, refresh: refreshReview } = useResource<DailyReview>(reviewUrl, revision)
const matches = computed(() => list.resolvedUrl.value?.startsWith(listPath.value + '&') ? list.data.value : null)
const matchRows = computed(() => (matches.value?.matches ?? []).map(match => {
  const bonds = (match.bonds ?? []).filter(bond => bond.layers > 0)
    .sort((a, b) => b.layers - a.layers || a.name.localeCompare(b.name, 'zh-CN'))
  return {
    ...match,
    defeatedBosses: [...new Set((match.bosses ?? []).map(bossName))],
    previewBonds: bonds.slice(0, BOND_PREVIEW_LIMIT),
    extraBonds: Math.max(0, bonds.length - BOND_PREVIEW_LIMIT),
  }
}))

const rate = computed(() => overview.value?.matches ? overview.value.wins / overview.value.matches : 0)
const dailyPoint = computed(() => overview.value?.points[0])
const peakIcon = computed(() => BOND_ICONS[pickMajorBond(overview.value?.peak?.names ?? [])])

function openMatch(id: string) {
  detailUrl.value = '/matches/' + id
}

function changePageSize(size: number) {
  pageSize.value = size
  page.value = 1
}
</script>

<template>
  <div class="daily">
    <div class="daily-date split">
      <time :datetime="day">{{ day }}</time>
    </div>

    <p v-if="pending" class="daily-status muted" role="status">正在汇总昨日战绩…</p>
    <p v-if="error" class="load-message" role="alert">{{ error }} <button type="button" @click="refresh">重试</button></p>

    <div v-if="overview?.matches" class="daily-summary">
      <section class="panel daily-score" aria-labelledby="daily-score-title">
        <h2 id="daily-score-title">作战表现</h2>
        <div class="daily-score-grid">
          <div class="daily-rate">
            <span>胜率</span>
            <strong>{{ percent(rate) }}</strong>
          </div>
          <dl class="daily-totals">
            <div><dt>总对局</dt><dd>{{ number(overview.matches) }}</dd></div>
            <div><dt>胜场</dt><dd class="win">{{ number(overview.wins) }}</dd></div>
            <div><dt>负场</dt><dd class="loss">{{ number(overview.matches - overview.wins) }}</dd></div>
          </dl>
        </div>
        <div class="daily-meter" aria-hidden="true"><i :style="{ width: rate * 100 + '%' }"></i></div>
        <dl class="daily-trophies">
          <div>
            <!-- 奖杯只在联合模拟通关时获得、不会扣减，所以写「获得奖杯」而不是带正负号的变化量。 -->
            <dt><TrophyIcon :badge="overview.trophy_badge" :total="overview.trophy_total?.total" :size="25" />获得奖杯</dt>
            <dd>{{ number(overview.trophy_change ?? null) }}</dd>
          </div>
        </dl>
      </section>

      <section class="panel daily-highlights" aria-labelledby="daily-highlights-title">
        <h2 id="daily-highlights-title">昨日亮点</h2>
        <dl class="daily-highlight-grid">
          <div>
            <dt>单局最高盟约总层数</dt>
            <dd>{{ overview.max_layers === null ? '—' : `${number(overview.max_layers)} 层` }}</dd>
          </div>
          <div>
            <dt>单项最高盟约</dt>
            <dd v-if="overview.peak" class="daily-peak">
              <img v-if="peakIcon" :src="peakIcon" width="28" height="28" alt="">
              <span>{{ overview.peak.names.join('、') }} <b>{{ number(overview.peak.layers) }} 层</b></span>
            </dd>
            <dd v-else>—</dd>
          </div>
          <div><dt>场均击杀</dt><dd>{{ number(dailyPoint?.kills ?? null) }}</dd></div>
          <div><dt>金币总花费</dt><dd>{{ number(overview.total_coins) }}</dd></div>
        </dl>
      </section>
    </div>

    <p v-if="reviewPending && overview?.matches" class="daily-status muted" role="status">正在汇总盟约与复盘数据…</p>
    <p v-if="reviewError" class="load-message" role="alert">{{ reviewError }} <button type="button" @click="refreshReview">重试</button></p>
    <div v-if="review && (review.wins.matches || review.losses.matches)" class="daily-summary">
      <BondShareChart :bonds="review.bonds" description="昨日累计层数占比" />
      <DailyReviewPanel :review="review" :url="reviewUrl" @open="openMatch" />
    </div>

    <section class="panel daily-matches" aria-labelledby="daily-matches-title" :aria-busy="list.pending.value">
      <header class="split daily-list-heading">
        <h2 id="daily-matches-title">昨日对局</h2>
        <span v-if="matches" class="muted">
          {{ number(matches.total) }} 局<span v-if="overview?.excluded"> · 已排除 {{ number(overview.excluded) }} 局疑似直接退出</span>
        </span>
      </header>
      <p v-if="list.pending.value && !matches" class="daily-status muted" role="status">正在读取对局…</p>
      <p v-if="list.error.value" class="load-message daily-list-error" role="alert">
        {{ list.error.value }} <button type="button" @click="list.refresh">重试</button>
      </p>

      <ul v-if="matchRows.length" class="daily-list">
        <li v-for="match in matchRows" :key="match.id">
          <button type="button" class="daily-match" @click="openMatch(match.id)">
            <time :datetime="match.played_at">{{ clockTime(match.played_at) }}</time>
            <span class="chip" :class="{ loss: match.result === 'loss' }">{{ resultLabel(match.result) }}</span>
            <span class="daily-mode">
              <b><TierTag :label="difficultyLabel(match.difficulty)" /></b>
              <span class="muted">{{ match.play }}</span>
            </span>
            <span v-if="match.strategy" class="daily-strategy">
              <img v-if="strategyIcon(match.strategy)" :src="strategyIcon(match.strategy)" width="22" height="22" alt="">
              {{ strategyOf(match.strategy) }}
            </span>
            <span class="daily-match-metrics">
              <span v-if="match.rounds !== null">{{ number(match.rounds) }} 回合</span>
              <span>{{ number(match.bond_layers) }} 层盟约</span>
            </span>
            <NIcon :component="ChevronForwardOutline" class="daily-arrow" aria-hidden="true" />
            <span v-if="match.defeatedBosses.length || match.previewBonds.length" class="daily-breakdown">
              <span v-if="match.defeatedBosses.length" class="daily-tags">
                <span class="daily-tag-label">击破</span>
                <BossLabel v-for="boss in match.defeatedBosses" :key="boss" :name="boss" class="daily-tag" />
              </span>
              <span v-if="match.previewBonds.length" class="daily-tags">
                <span class="daily-tag-label">盟约</span>
                <span v-for="(bond, index) in match.previewBonds" :key="index" class="daily-tag daily-bond">
                  <img v-if="BOND_ICONS[bond.name]" :src="BOND_ICONS[bond.name]" width="17" height="17" alt="">
                  {{ bond.name }} <b>{{ number(bond.layers) }}</b>
                </span>
                <span v-if="match.extraBonds" class="daily-tag-label">另 {{ match.extraBonds }} 种</span>
              </span>
            </span>
          </button>
        </li>
      </ul>
      <div v-else-if="matches && !list.pending.value && !list.error.value" class="daily-empty">
        <h3>昨日暂无可统计对局</h3>
        <p v-if="overview?.excluded">昨天的记录均被标记为疑似直接退出。</p>
        <p v-else>导入或同步战绩后，昨天的对局会显示在这里。</p>
        <RouterLink class="button-link" to="/import">前往数据导入</RouterLink>
      </div>
      <ListPagination v-if="matches && matches.total > 10" :page="matches.page" :page-size="pageSize" :total="matches.total"
        :disabled="list.pending.value" @update:page="page = $event" @update:page-size="changePageSize" />
    </section>

  </div>

  <MatchReport v-if="detailUrl" :detail="report.data.value" :pending="report.pending.value"
    :error="report.error.value" @close="detailUrl = null" @retry="report.refresh" />
</template>

<style scoped>
.daily { display: grid; gap: 1rem; }
.daily-date { gap: .3rem 1rem; flex-wrap: wrap; color: var(--muted); font-size: .875rem; }
.daily-date time { color: var(--text); font: 600 1.15rem var(--numbers); letter-spacing: .08em; }
.daily-summary { display: grid; grid-template-columns: 1.06fr 1fr; gap: 1rem; }
.daily-score, .daily-highlights { padding: 1.2rem clamp(1rem, 2.5vw, 1.65rem); }
.daily-score {
  border-top-color: var(--accent);
  background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, var(--panel)), var(--panel) 66%);
}
.daily-score-grid { display: flex; align-items: end; justify-content: space-between; gap: .9rem 1.5rem; margin-top: 1.15rem; }
.daily-rate { display: grid; gap: .25rem; }
.daily-rate span, .daily-totals dt { color: var(--muted); font-size: .82rem; }
.daily-highlight-grid dt { color: var(--muted); font-size: .95rem; }
.daily-rate strong {
  color: var(--text);
  font: 700 clamp(2.75rem, 5vw, 4.5rem)/.95 var(--numbers);
  letter-spacing: -.035em;
  font-variant-numeric: tabular-nums;
}
.daily-totals { display: flex; gap: clamp(.8rem, 3vw, 2rem); }
.daily-totals dt { white-space: nowrap; }
.daily-totals dd { font: 650 1.5rem/1.2 var(--numbers); }
.daily-totals .win { color: var(--win); }
.daily-totals .loss { color: var(--loss); }
.daily-meter { height: 5px; margin-top: 1.2rem; background: color-mix(in srgb, var(--loss) 48%, var(--inset)); }
.daily-meter i { display: block; height: 100%; background: var(--win); }
.daily-trophies { border-top: 1px solid var(--line); margin-top: .75rem; padding-top: .55rem; }
.daily-trophies > div, .daily-trophies dt { display: flex; align-items: center; gap: .5rem; }
.daily-trophies > div { justify-content: space-between; }
.daily-trophies dt { font-size: .85rem; color: var(--muted); }
.daily-trophies dd { color: var(--text); font: 700 1.5rem/1 var(--numbers); }
.daily-trophies .loss { color: var(--loss); }
.daily-highlight-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .7rem 1rem; margin-top: .75rem; }
.daily-highlight-grid > div { padding-top: .45rem; border-top: 1px solid var(--line); }
.daily-highlight-grid dd { margin-top: .15rem; font: 650 clamp(1.18rem, 1.9vw, 1.48rem)/1.3 var(--numbers); }
.daily-peak { display: flex; align-items: center; gap: .35rem; }
.daily-peak img { flex: none; object-fit: contain; }
.daily-peak b { white-space: nowrap; }
/* 并列多个盟约时名字会挤成两行，名字降一号，层数保持醒目。 */
.daily-peak span { font-size: .95rem; line-height: 1.35; }
.daily-peak b { font-size: 1.3rem; }
.daily-list-heading { padding: .9rem 1.15rem; flex-wrap: wrap; gap: .3rem .8rem; }
.daily-list-heading .muted { font-size: .83rem; }
.daily-list { margin: 0; padding: 0; list-style: none; }
.daily-list li { border-top: 1px solid var(--line); }
.daily-match {
  width: 100%;
  display: grid;
  grid-template-columns: 4.3rem 2.6rem minmax(0, 1.2fr) minmax(0, 1fr) auto 1rem;
  justify-items: start;
  gap: .3rem 1rem;
  padding: .7rem 1.15rem;
  border: 0;
  background: transparent;
  color: var(--text);
  text-align: left;
  white-space: normal;
}
.daily-match:hover { background: color-mix(in srgb, var(--accent) 7%, var(--panel)); color: var(--text); }
.daily-match:focus-visible { outline-offset: -2px; }
.daily-match time { font: 650 1.1rem var(--numbers); }
.daily-mode { grid-column: 3; display: flex; align-items: center; gap: .2rem .75rem; flex-wrap: wrap; }
.daily-match-metrics { color: var(--muted); }
.daily-strategy { grid-column: 4; display: flex; align-items: center; gap: .4rem; }
.daily-mode, .daily-strategy, .daily-peak { overflow-wrap: anywhere; }
.daily-strategy img { flex: none; object-fit: contain; }
.daily-match-metrics { grid-column: 5; display: flex; flex-wrap: wrap; gap: .15rem .85rem; font-size: .82rem; }
.daily-arrow { grid-column: 6; color: var(--muted); }
.daily-breakdown { grid-column: 3 / 6; display: flex; flex-wrap: wrap; gap: .3rem 1rem; margin-top: .15rem; }
.daily-tags { display: flex; flex-wrap: wrap; align-items: center; gap: .25rem; }
.daily-tag-label { color: var(--muted); font-size: .75rem; margin-inline: .1rem .25rem; }
.daily-tag { display: inline-flex; align-items: center; gap: .2rem; padding: .12rem .35rem; background: var(--inset); border: 1px solid var(--line); border-radius: 2px; font-size: .78rem; overflow-wrap: anywhere; }
.daily-tag img { flex: none; object-fit: contain; }
:root[data-theme="light"] .daily-bond img { filter: brightness(0) opacity(.82); }
.daily-tag b { color: var(--accent); }
.daily-match:hover .daily-arrow { color: var(--accent); }
.daily-status { padding: .5rem 1.15rem .9rem; }
.daily-list-error { margin-inline: 1.15rem; }
.daily-empty { display: grid; justify-items: center; gap: .5rem; border-top: 1px solid var(--line); padding: 2rem 1rem; text-align: center; }
.daily-empty p { color: var(--muted); }
.daily-empty a { margin-top: .35rem; }
.daily .load-message { margin-block-end: 0; }
@media (max-width: 900px) {
  .daily-score-grid { flex-wrap: wrap; }
}
@media (max-width: 730px) {
  .daily-summary { grid-template-columns: minmax(0, 1fr); }
  .daily-match {
    grid-template-columns: 3rem 2rem minmax(0, 1fr) 1rem;
    gap: .25rem .55rem;
    padding-inline: .8rem;
  }
  .daily-strategy, .daily-match-metrics { grid-column: 3; }
  .daily-breakdown { grid-column: 1 / -1; }
  .daily-arrow { grid-column: 4; grid-row: 1; }
  .daily-list-heading { padding-inline: .8rem; }
}
@media (max-width: 360px) {
  .daily-score-grid { align-items: start; }
  .daily-rate strong { font-size: 2.45rem; }
}
</style>
