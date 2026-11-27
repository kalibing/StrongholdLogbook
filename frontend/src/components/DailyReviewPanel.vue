<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import { ChevronForwardOutline, FlameOutline, TimeOutline } from '@vicons/ionicons5'
import { api, message } from '../api'
import { BOSS_MARKS } from '../assets'
import { clockTime, difficultyLabel, number } from '../format'
import type { DailyReview } from '../models'
import BossLabel from './BossLabel.vue'

const props = defineProps<{ review: DailyReview; url: string }>()
const emit = defineEmits<{ open: [id: string] }>()
const analysis = ref('')
const error = ref('')
const pending = ref(false)
const request = new AbortController()
const bosses = computed(() => props.review.bosses ?? [])
const duration = computed(() => {
  const seconds = props.review.total_duration_seconds
  if (seconds == null) return '—'
  if (seconds < 60) return `${number(seconds)} 秒`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor(seconds / 60) % 60
  return `${hours ? `${number(hours)} 小时 ` : ''}${minutes} 分`
})
// 关键对局：击杀、盟约层数、金币花费三项之最（不列败局）。每项各占一行，同一局拿下多项也分开列。
const keyMatches = computed(() => {
  const { most_kills, most_layers, most_coins } = props.review
  return [
    most_kills && { key: 'kills', id: most_kills.id, played_at: most_kills.played_at, difficulty: most_kills.difficulty, label: '最高击杀', value: `${number(most_kills.kills)} 次击杀` },
    most_layers && { key: 'layers', id: most_layers.id, played_at: most_layers.played_at, difficulty: most_layers.difficulty, label: '盟约最高', value: `${number(most_layers.layers)} 层盟约` },
    most_coins && { key: 'coins', id: most_coins.id, played_at: most_coins.played_at, difficulty: most_coins.difficulty, label: '金币最多', value: `${number(most_coins.coins)} 金币` },
  ].filter(pick => !!pick)
})

onBeforeUnmount(() => request.abort())

async function generate() {
  pending.value = true
  error.value = ''
  try {
    const result = await api<{ analysis: string }>(props.url, { method: 'POST', signal: request.signal })
    if (!request.signal.aborted) analysis.value = result.analysis
  } catch (reason) {
    if (!request.signal.aborted) error.value = message(reason)
  } finally {
    if (!request.signal.aborted) pending.value = false
  }
}
</script>

<template>
  <section class="panel daily-review" aria-labelledby="daily-review-title">
    <header class="split review-heading">
      <h2 id="daily-review-title">战报复盘</h2>
      <NButton v-if="review.ai_available && !analysis" secondary size="small" :loading="pending" @click="generate">
        {{ error ? '重试 AI 分析' : '生成 AI 分析' }}
      </NButton>
    </header>
    <dl class="review-metrics">
      <div>
        <dt><NIcon :component="FlameOutline" aria-hidden="true" />最长连胜</dt>
        <dd>{{ number(review.longest_win_streak ?? null) }} <small>局</small></dd>
      </div>
      <div title="仅统计有时长记录的对局">
        <dt><NIcon :component="TimeOutline" aria-hidden="true" />已记录用时</dt><dd>{{ duration }}</dd>
      </div>
    </dl>
    <div v-if="keyMatches.length" class="review-matches">
      <h3>关键对局</h3>
      <button v-for="match in keyMatches" :key="match.key" type="button" class="review-match" @click="emit('open', match.id)">
        <span class="review-match-copy">
          <strong>{{ match.label }}</strong>
          <span>{{ clockTime(match.played_at) }} · {{ difficultyLabel(match.difficulty) }}</span>
        </span>
        <b v-if="match.value">{{ match.value }}</b>
        <NIcon :component="ChevronForwardOutline" aria-hidden="true" />
      </button>
    </div>
    <details v-if="bosses.length" class="review-bosses">
      <summary>
        <strong>首领击破</strong>
        <span title="同一局击破两类首领时，两类各计一局">
          <span><img :src="BOSS_MARKS.normal" width="16" height="16" alt="普通首领">{{ number(review.normal_matches ?? null) }} 局</span>
          <span><img :src="BOSS_MARKS.hidden" width="16" height="16" alt="隐藏首领">{{ number(review.hidden_matches) }} 局</span>
        </span>
      </summary>
      <ul>
        <li v-for="boss in bosses" :key="boss.name">
          <BossLabel :name="boss.name" :hidden="boss.hidden" :size="23" />
          <b>{{ number(boss.matches) }} <small>局</small></b>
        </li>
      </ul>
    </details>
    <p v-if="review.ai_available && !analysis" class="review-service muted">点击后将昨日战绩摘要发送至已配置的模型服务。</p>
    <p v-if="error" class="review-error" role="alert">{{ error }}</p>
    <div v-if="analysis" class="review-analysis" role="status"><h3>AI 分析</h3><p>{{ analysis }}</p></div>
  </section>
</template>

<style scoped>
.daily-review { padding: 1.2rem clamp(1rem, 2.5vw, 1.65rem); }
.review-heading { flex-wrap: wrap; }
.review-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem; margin-block: .7rem; }
.review-metrics > div { padding: .55rem .7rem; border: 1px solid var(--line); border-radius: var(--radius); background: var(--inset); }
.review-metrics dt { display: flex; align-items: center; gap: .4rem; color: var(--muted); font-size: .9375rem; }
.review-metrics dt i { color: var(--accent); }
.review-metrics dd { margin-top: .3rem; font: 500 1.25rem/1.15 var(--numbers); overflow-wrap: anywhere; }
.review-metrics small, .review-bosses small { font-size: .8125rem; font-weight: 400; }
.review-bosses { margin-top: .65rem; border-top: 1px solid var(--line); }
.review-bosses summary { cursor: pointer; padding-block: .45rem; font-size: .9375rem; }
.review-bosses summary > span { float: inline-end; display: inline-flex; gap: .55rem; color: var(--muted); }
.review-bosses summary > span span { display: inline-flex; align-items: center; gap: .15rem; }
.review-bosses img { object-fit: contain; }
.review-bosses ul { list-style: none; margin: 0; padding: 0; max-height: 12rem; overflow-y: auto; }
.review-bosses li { display: flex; justify-content: space-between; align-items: center; gap: .5rem; padding-block: .23rem; border-top: 1px solid var(--line); font-size: .9375rem; }
.review-bosses li b { flex: none; font-family: var(--numbers); }
.review-matches { display: grid; gap: .38rem; }
.review-matches h3 { color: var(--muted); font-size: .9375rem; }
.review-match {
  display: flex; align-items: center; gap: .55rem; min-width: 0; width: 100%;
  padding: .42rem .6rem; text-align: left; white-space: normal; background: var(--inset);
}
.review-match-copy { display: grid; gap: .1rem; flex: 1; }
.review-match-copy strong { font-size: .9375rem; }
.review-match-copy span { color: var(--muted); font-size: .9375rem; }
.review-match b { color: var(--accent); text-align: right; font: 500 1rem var(--numbers); }
.review-match > i { flex: none; }
.review-service, .review-error { margin-top: .6rem; font-size: .9375rem; }
.review-error { color: var(--loss); }
.review-analysis { padding-top: .7rem; margin-top: .75rem; border-top: 1px solid var(--line); }
.review-analysis p { white-space: pre-wrap; overflow-wrap: anywhere; margin-top: .35rem; }
</style>
