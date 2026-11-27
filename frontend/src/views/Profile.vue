<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logbook } from '../context'
import { useResource } from '../api'
import { number, percent, resultLabel } from '../format'
import { portrait } from '../icons'
import { strategyIcon, strategyOf, unitOf } from '../bands'
import type { Profile } from '../models'
import AvatarImage from '../components/AvatarImage.vue'
import TierTag from '../components/TierTag.vue'
import TrophyIcon from '../components/TrophyIcon.vue'

const { revision } = logbook()
const { data, pending, error, refresh } = useResource<Profile>(ref('/profile'), revision, true)

/** PRTS：累计奖杯 0 / 10 / 30 / 60 / 100 / 150 / 200 / 300+ 对应奖杯 1–8 级，与 TrophyIcon 一致。 */
const THRESHOLDS = [0, 10, 30, 60, 100, 150, 200, 300]
const trophy = computed(() => {
  const total = data.value?.trophy_total?.total
  if (total == null) return null
  const level = data.value?.trophy_badge?.level ?? (THRESHOLDS.filter(value => total >= value).length || 1)
  const next = THRESHOLDS.find(value => value > total) ?? null
  const floor = [...THRESHOLDS].reverse().find(value => value <= total) ?? 0
  return { total, level, next, progress: next === null ? 1 : (total - floor) / (next - floor) }
})

const displayName = computed(() => data.value?.account?.nickname || data.value?.username || '')
const initial = computed(() => Array.from(displayName.value)[0]?.toUpperCase() ?? '?')

function duration(seconds: number | null) {
  if (seconds == null) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  return hours ? `${hours} 小时 ${minutes} 分` : `${minutes} 分`
}

const tiles = computed(() => {
  const career = data.value?.career
  const streaks = data.value?.streaks
  if (!career || !streaks) return []
  const current = streaks.current
  return [
    { label: '总对局', value: number(career.matches), hint: career.excluded ? `已排除 ${career.excluded} 局疑似直接退出` : '' },
    { label: '胜率', value: career.win_rate == null ? '—' : percent(career.win_rate), hint: `${career.wins} 胜 ${career.losses} 负`, accent: true },
    { label: '活跃天数', value: number(career.active_days), hint: career.first_day ? `${career.first_day} 起` : '' },
    { label: '累计时长', value: duration(career.play_seconds), hint: '有时长记录的对局' },
    { label: '最长连胜', value: `${streaks.best_win} 局`, hint: '' },
    {
      label: '当前状态', value: current ? `${current.count} 连${resultLabel(current.result)}` : '—',
      hint: career.last_day ? `最近一局 ${career.last_day}` : '', loss: current?.result === 'loss',
    },
  ]
})

const records = computed(() => {
  const career = data.value?.career
  if (!career) return []
  return [
    { label: '单局最高击杀', value: number(career.max_kills) },
    { label: '单局最高盟约层数', value: career.max_layers == null ? '—' : `${career.max_layers} 层` },
    { label: '累计击杀', value: number(career.total_kills) },
  ]
})

/** 活跃热力图：按周分列，周一在上；颜色按当天局数分四档。 */
const heat = computed(() => (data.value?.activity.days ?? []).map(entry => ({
  ...entry, level: entry.count === 0 ? 0 : entry.count <= 2 ? 1 : entry.count <= 4 ? 2 : entry.count <= 7 ? 3 : 4,
})))
const activeDays = computed(() => heat.value.filter(entry => entry.count).length)

// 窄屏时热力图横向滚动：默认停在最右（最近几周），而不是一年前的空白。
const heatWrap = ref<HTMLElement | null>(null)
watch(heatWrap, element => { if (element) element.scrollLeft = element.scrollWidth })
</script>

<template>
  <p v-if="error" class="table-feedback load-message" role="alert">
    {{ error }} <span v-if="data">正在显示上次成功的结果。</span> <button type="button" @click="refresh">重试</button>
  </p>
  <div v-if="!data && pending" class="loading-shell" role="status">正在读取主页…</div>

  <div v-if="data" class="profile" :aria-busy="pending">
    <section class="panel profile-id" aria-labelledby="profile-name">
      <div class="profile-emblem" aria-hidden="true"><span>{{ initial }}</span></div>
      <div class="profile-who">
        <h2 id="profile-name">
          {{ displayName }}<small v-if="data.account?.nick_number" class="profile-number">#{{ data.account.nick_number }}</small>
        </h2>
        <p class="muted">
          站内账号 {{ data.username }}
          <template v-if="data.account?.level"> · 博士等级 {{ data.account.level }}</template>
        </p>
        <ul v-if="data.account" class="profile-badges">
          <li><b>{{ number(data.account.likes ?? null) }}</b>获赞</li>
          <li><b>{{ data.account.titles }}</b>称号</li>
        </ul>
        <p v-else class="profile-bind muted">
          绑定<RouterLink to="/achievements">成就档案</RouterLink>后显示游戏昵称、等级与获赞。
        </p>
      </div>
      <div v-if="trophy" class="profile-trophy"
        :title="data.trophy_total?.source === 'profile' ? '来自成就档案的累计奖杯' : '按已导入对局的奖杯记录累计'">
        <TrophyIcon :badge="data.trophy_badge" :total="trophy.total" :size="76" />
        <div>
          <span class="profile-trophy-label">奖杯总数 · {{ trophy.level }} 级</span>
          <strong>{{ number(trophy.total) }}</strong>
          <span class="profile-trophy-bar" aria-hidden="true"><i :style="{ width: trophy.progress * 100 + '%' }"></i></span>
          <small class="muted">{{ trophy.next === null ? '已达最高档' : `距下一档还差 ${trophy.next - trophy.total}` }}</small>
        </div>
      </div>
    </section>

    <section class="profile-tiles" aria-label="生涯数据">
      <div v-for="tile in tiles" :key="tile.label" class="panel profile-tile">
        <span class="profile-tile-label">{{ tile.label }}</span>
        <strong :class="{ 'profile-accent': tile.accent, 'profile-loss': tile.loss }">{{ tile.value }}</strong>
        <small v-if="tile.hint" class="muted">{{ tile.hint }}</small>
      </div>
    </section>

    <div class="profile-grid">
      <section class="panel profile-card" aria-labelledby="profile-best">
        <h2 id="profile-best">最高通关</h2>
        <dl class="profile-best">
          <div><dt>联合模拟</dt><dd><TierTag v-if="data.best.union" :label="data.best.union" :size="26" /><span v-else class="muted">暂无</span></dd></div>
          <div><dt>独立模拟</dt><dd><TierTag v-if="data.best.solo" :label="data.best.solo" :size="26" /><span v-else class="muted">暂无</span></dd></div>
        </dl>
        <h3>模拟方式</h3>
        <ul class="profile-plays">
          <li v-for="play in data.plays" :key="play.play">
            <span>{{ play.play }}</span>
            <span class="profile-play-bar" aria-hidden="true">
              <i :style="{ width: (play.matches / Math.max(1, data.career.matches)) * 100 + '%' }"></i>
            </span>
            <span class="muted">{{ play.matches }} 局 · 胜率 {{ percent(play.wins / play.matches) }}</span>
          </li>
          <li v-if="!data.plays.length" class="muted">还没有对局。</li>
        </ul>
      </section>

      <section class="panel profile-card" aria-labelledby="profile-form">
        <h2 id="profile-form">近期状态</h2>
        <p class="profile-results" :aria-label="`最近 ${data.recent_results.length} 局`">
          <span v-for="(result, index) in data.recent_results" :key="index" class="chip" :class="{ loss: result === 'loss' }">{{ resultLabel(result) }}</span>
          <span v-if="!data.recent_results.length" class="muted">还没有对局。</span>
        </p>
        <h3>生涯纪录</h3>
        <dl class="profile-records">
          <div v-for="record in records" :key="record.label"><dt>{{ record.label }}</dt><dd>{{ record.value }}</dd></div>
        </dl>
      </section>
    </div>

    <section class="panel profile-card" aria-labelledby="profile-activity">
      <div class="split">
        <h2 id="profile-activity">活跃度</h2>
        <span class="period">{{ data.activity.start }} — {{ data.activity.end }} · {{ activeDays }} 天有对局</span>
      </div>
      <div ref="heatWrap" class="profile-heat-wrap">
        <ol class="profile-heat-days" aria-hidden="true"><li>一</li><li></li><li>三</li><li></li><li>五</li><li></li><li>日</li></ol>
        <ol class="profile-heat">
          <li v-for="entry in heat" :key="entry.day" :class="`heat-${entry.level}`" :title="`${entry.day} · ${entry.count} 局`">
            <span class="sr-only">{{ entry.day }} {{ entry.count }} 局</span>
          </li>
        </ol>
      </div>
      <p class="profile-heat-legend muted" aria-hidden="true">
        少 <i class="heat-0"></i><i class="heat-1"></i><i class="heat-2"></i><i class="heat-3"></i><i class="heat-4"></i> 多
      </p>
    </section>

    <div class="profile-grid">
      <section class="panel profile-card" aria-labelledby="profile-operators">
        <div class="split">
          <h2 id="profile-operators">本命干员</h2>
          <RouterLink class="period profile-more" to="/operators">完整出场榜</RouterLink>
        </div>
        <ol class="profile-ops">
          <li v-for="(operator, index) in data.operators" :key="operator.id">
            <span class="profile-rank">{{ index + 1 }}</span>
            <AvatarImage :src="portrait(operator.id)" :name="operator.name" :size="44" />
            <span class="profile-op-name">{{ operator.name }}<small class="muted">{{ operator.count }} 局 · 胜率 {{ percent(operator.win_rate) }}</small></span>
          </li>
          <li v-if="!data.operators.length" class="muted">还没有阵容明细。</li>
        </ol>
      </section>

      <section class="panel profile-card" aria-labelledby="profile-strategies">
        <div class="split">
          <h2 id="profile-strategies">常用策略</h2>
          <RouterLink class="period profile-more" :to="{ name: 'operators', query: { view: 'strategies' } }">完整策略列表</RouterLink>
        </div>
        <ol class="profile-ops">
          <li v-for="(strategy, index) in data.strategies" :key="strategy.name" :title="unitOf(strategy.name) || undefined">
            <span class="profile-rank">{{ index + 1 }}</span>
            <img v-if="strategyIcon(strategy.name)" class="strategy-icon profile-strategy-icon" :src="strategyIcon(strategy.name)" alt="">
            <span class="profile-op-name">{{ strategyOf(strategy.name) }}<small class="muted">{{ strategy.count }} 局 · 胜率 {{ percent(strategy.win_rate) }}</small></span>
          </li>
          <li v-if="!data.strategies.length" class="muted">还没有策略记录。</li>
        </ol>
      </section>
    </div>
  </div>
</template>

<style scoped>
.profile { display: grid; gap: 1rem; }
.profile h2 { font-size: 1.1rem; }
.profile h3 { margin: 1.1rem 0 .55rem; color: var(--muted); font-size: .82rem; font-weight: 600; }
.profile-card { padding: 1.1rem 1.25rem 1.25rem; }
.profile-card .split { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
.profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }

/* —— 身份卡 —— */
.profile-id {
  position: relative; overflow: hidden;
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 1.25rem;
  padding: 1.35rem 1.5rem;
}
.profile-id::before {
  content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--accent);
}
.profile-emblem {
  display: grid; place-items: center; width: 84px; height: 84px; flex: none;
  clip-path: polygon(30% 0, 70% 0, 100% 30%, 100% 70%, 70% 100%, 30% 100%, 0 70%, 0 30%);
  background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 35%, var(--panel)));
}
.profile-emblem span {
  display: grid; place-items: center; width: 78px; height: 78px;
  clip-path: inherit; background: var(--inset);
  color: var(--accent); font: 800 2.2rem/1 var(--numbers);
}
.profile-who { display: grid; gap: .3rem; min-width: 0; }
.profile-who h2 { font-size: 1.6rem; overflow-wrap: anywhere; }
.profile-number { margin-left: .5rem; color: var(--muted); font: 500 .95rem var(--numbers); }
.profile-badges { display: flex; gap: .5rem; margin: .3rem 0 0; padding: 0; list-style: none; }
.profile-badges li {
  display: inline-flex; align-items: baseline; gap: .35rem; padding: .2rem .6rem;
  border: 1px solid var(--line); border-radius: 2px; background: var(--inset); color: var(--muted); font-size: .8rem;
}
.profile-badges b { color: var(--text); font: 700 .95rem var(--numbers); }
.profile-bind a { color: var(--accent); margin: 0 .15rem; }
.profile-trophy { display: flex; align-items: center; gap: .9rem; padding-left: 1.25rem; border-left: 1px solid var(--line); }
.profile-trophy > div { display: grid; gap: .25rem; min-width: 9rem; }
.profile-trophy-label { color: var(--muted); font-size: .8rem; }
.profile-trophy strong { color: var(--accent); font: 700 2.1rem/1 var(--numbers); }
.profile-trophy-bar, .profile-play-bar { display: block; height: 4px; background: var(--inset); border-radius: 2px; overflow: hidden; }
.profile-trophy-bar i, .profile-play-bar i { display: block; height: 100%; background: var(--accent); }
.profile-trophy small { font-size: .75rem; }

/* —— 数据格 —— */
.profile-tiles { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: .75rem; }
.profile-tile { display: grid; align-content: start; gap: .3rem; padding: .9rem 1rem; }
.profile-tile-label { color: var(--muted); font-size: .8rem; }
.profile-tile strong { font: 700 1.45rem/1.15 var(--numbers); white-space: nowrap; }
.profile-tile small { font-size: .74rem; }
.profile-accent { color: var(--accent); }
.profile-loss { color: var(--loss); }

/* —— 最高通关 / 模拟方式 —— */
.profile-best { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; margin-top: .8rem; }
.profile-best > div { padding: .75rem .9rem; border: 1px solid var(--line); border-radius: 2px; background: var(--inset); }
.profile-best dt { color: var(--muted); font-size: .8rem; margin-bottom: .35rem; }
.profile-best dd { font-weight: 700; font-size: 1.05rem; }
.profile-plays { display: grid; gap: .55rem; margin: 0; padding: 0; list-style: none; }
.profile-plays li { display: grid; grid-template-columns: 5rem minmax(0, 1fr) auto; align-items: center; gap: .75rem; font-size: .88rem; }

/* —— 近期状态 —— */
.profile-results { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .8rem; }
.profile-records { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
.profile-records > div { padding: .7rem .85rem; border: 1px solid var(--line); border-radius: 2px; background: var(--inset); }
.profile-records dt { color: var(--muted); font-size: .78rem; }
.profile-records dd { margin-top: .2rem; font: 700 1.2rem var(--numbers); }

/* —— 活跃热力图 —— */
.profile-heat-wrap { display: flex; gap: .4rem; margin-top: .9rem; overflow-x: auto; padding-bottom: .25rem; }
.profile-heat-days, .profile-heat { margin: 0; padding: 0; list-style: none; display: grid; grid-template-rows: repeat(7, 1fr); gap: 3px; }
.profile-heat-days { position: sticky; left: 0; z-index: 1; flex: none; padding-right: .3rem; background: var(--panel); color: var(--muted); font-size: .68rem; align-items: center; }
/* 一年 53 列铺满面板宽度；窄屏时每格至少 10px，横向滚动。 */
.profile-heat { flex: 1; min-width: calc(53 * 13px); grid-auto-flow: column; grid-auto-columns: minmax(10px, 1fr); }
.profile-heat li { aspect-ratio: 1; border-radius: 2px; }
.profile-heat-legend i { width: 12px; height: 12px; border-radius: 2px; }
.heat-0 { background: var(--inset); outline: 1px solid color-mix(in srgb, var(--line) 70%, transparent); outline-offset: -1px; }
.heat-1 { background: color-mix(in srgb, var(--accent) 28%, var(--inset)); }
.heat-2 { background: color-mix(in srgb, var(--accent) 52%, var(--inset)); }
.heat-3 { background: color-mix(in srgb, var(--accent) 76%, var(--inset)); }
.heat-4 { background: var(--accent); }
.profile-heat-legend { display: flex; align-items: center; justify-content: flex-end; gap: 4px; margin-top: .5rem; font-size: .74rem; }
.profile-heat-legend i { display: inline-block; }

/* —— 本命干员 / 常用策略 —— */
.profile-more { color: var(--accent); }
.profile-ops { display: grid; gap: .55rem; margin: .8rem 0 0; padding: 0; list-style: none; }
.profile-ops li { display: flex; align-items: center; gap: .75rem; }
.profile-rank { width: 1.4rem; color: var(--muted); font: 700 1rem var(--numbers); text-align: center; }
.profile-ops li:first-child .profile-rank { color: var(--accent); }
.profile-op-name { display: grid; font-weight: 650; }
.profile-op-name small { font-weight: 400; font-size: .78rem; }
.profile-strategy-icon { width: 44px; height: 44px; }

.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

@media (prefers-reduced-motion: no-preference) {
  .profile-trophy-bar i, .profile-play-bar i { animation: profile-grow .8s cubic-bezier(.2, .8, .2, 1) both; transform-origin: left; }
  .profile-heat li { animation: profile-pop .4s ease-out both; }
}
@keyframes profile-grow { from { transform: scaleX(0); } }
@keyframes profile-pop { from { opacity: 0; transform: scale(.4); } }

@media (max-width: 980px) {
  .profile-tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 730px) {
  .profile-grid { grid-template-columns: 1fr; }
  .profile-id { grid-template-columns: auto minmax(0, 1fr); }
  .profile-trophy { grid-column: 1 / -1; padding: 1rem 0 0; border-left: 0; border-top: 1px solid var(--line); }
  .profile-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .profile-records { grid-template-columns: 1fr; }
}
</style>
