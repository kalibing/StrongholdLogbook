<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { BOND_ICONS, BOSS_ICONS, ELITE_ICONS, EQUIPMENT_ICONS, STRATEGY_ICONS } from '../assets'
import { avatarFor, loadDirectory } from '../directory'
import { dateTime, difficultyLabel, number, resultLabel } from '../format'
import { portrait } from '../icons'
import type { MatchDetail } from '../models'

const props = defineProps<{ detail: MatchDetail | null; pending?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; retry: [] }>()

const dialog = ref<HTMLDialogElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const names = ref(new Map<string, string>())
const missingPortraits = reactive(new Set<string>())
const initiatorAvatar = computed(() => avatarFor(names.value, props.detail?.initiator ?? null))
const displayItem = (name: string) => name.startsWith('chess_item_') ? '未识别装备' : name
const itemCounts = (items: string[]) => {
  const counts = new Map<string, number>()
  for (const item of items) counts.set(item, (counts.get(item) ?? 0) + 1)
  return [...counts].map(([name, count]) => ({ name, count }))
}
const activeBonds = computed(() => (props.detail?.bonds ?? []).filter(bond => bond.layers > 0))
const totalLayers = computed(() => activeBonds.value.reduce((sum, bond) => sum + bond.layers, 0))
const duration = computed(() => {
  const seconds = props.detail?.duration_seconds
  if (!seconds) return '—'
  return Math.floor(seconds / 60) + ' 分 ' + seconds % 60 + ' 秒'
})
const meta = computed(() => props.detail
  ? [dateTime(props.detail.played_at), props.detail.play, difficultyLabel(props.detail.difficulty)]
  : [])

function close() {
  dialog.value?.close()
}

function retry() {
  closeButton.value?.focus()
  emit('retry')
}

onMounted(async () => {
  dialog.value?.showModal()
  names.value = await loadDirectory()
})
</script>

<template>
  <dialog ref="dialog" id="detail" aria-labelledby="detail-title" @close="emit('close')">
    <header class="report-heading">
      <div>
        <div class="report-title">
          <h2 id="detail-title">单局战报</h2>
          <span v-if="detail" class="chip" :class="{ loss: detail.result === 'loss' }">{{ resultLabel(detail.result) }}</span>
        </div>
        <p v-if="detail" class="report-meta">
          <span v-for="(item, index) in meta" :key="index">{{ item }}</span>
        </p>
      </div>
      <button ref="closeButton" type="button" autofocus @click="close">关闭</button>
    </header>

    <div class="report-body" :aria-busy="pending">
      <p v-if="pending" class="muted" role="status">正在读取战报…</p>
      <div v-else-if="error" class="report-error">
        <p role="alert">{{ error }}</p>
        <button type="button" @click="retry">重试</button>
      </div>

      <div v-else-if="detail" class="report-content">
        <dl class="report-stats">
          <div><dt>回合</dt><dd>{{ number(detail.rounds) }}</dd></div>
          <div><dt>击杀</dt><dd>{{ number(detail.kills) }}</dd></div>
          <div><dt>金币花费</dt><dd>{{ number(detail.coins) }}</dd></div>
          <div><dt>同步次数</dt><dd>{{ number(detail.sync_count) }}</dd></div>
          <div><dt>时长</dt><dd>{{ duration }}</dd></div>
          <div><dt>奖杯变化</dt><dd>{{ number(detail.trophies) }}</dd></div>
        </dl>

        <dl v-if="detail.strategy || detail.initiator" class="report-setup">
          <div v-if="detail.strategy">
            <dt>开局策略</dt>
            <dd>
              <img v-if="STRATEGY_ICONS[detail.strategy]" :src="STRATEGY_ICONS[detail.strategy]" width="24" height="24" alt="">
              {{ detail.strategy }}
            </dd>
          </div>
          <div v-if="detail.initiator">
            <dt>发起干员</dt>
            <dd>
              <img v-if="initiatorAvatar && !missingPortraits.has(initiatorAvatar)" :src="initiatorAvatar" width="24" height="24" alt=""
                @error="missingPortraits.add(initiatorAvatar)">
              <span v-else class="report-avatar-fallback report-avatar-fallback--small" aria-hidden="true">{{ detail.initiator.slice(0, 1) }}</span>
              {{ detail.initiator }}
            </dd>
          </div>
        </dl>

        <div class="report-breakdown">
          <section class="report-section">
            <h3>盟约 <small>{{ activeBonds.length }} 种 · {{ totalLayers }} 层</small></h3>
            <div v-if="activeBonds.length" class="bond-grid">
              <div v-for="bond in activeBonds" :key="bond.name">
                <span class="bond-label">
                  <img v-if="BOND_ICONS[bond.name]" :src="BOND_ICONS[bond.name]" width="23" height="23" alt="" @error="($event.target as HTMLImageElement).style.display = 'none'">
                  <span>{{ bond.name }}</span>
                </span>
                <b>{{ bond.layers }} 层</b>
              </div>
            </div>
            <p v-else class="muted">无盟约记录</p>
          </section>

          <section class="report-section">
            <h3>已击杀首领</h3>
            <div v-if="detail.bosses.length" class="boss-grid">
              <div v-for="boss in detail.bosses" :key="boss" class="art-card">
                <img v-if="BOSS_ICONS[boss]" :src="BOSS_ICONS[boss]" width="42" height="42" alt="" @error="($event.target as HTMLImageElement).style.display = 'none'">
                <b>{{ boss }}</b>
              </div>
            </div>
            <p v-else class="muted">无首领击杀记录</p>
          </section>
        </div>

        <section class="report-section">
          <h3>最终阵容</h3>
          <ul v-if="detail.squad.length" class="squad">
            <li v-for="(unit, index) in detail.squad" :key="unit.id + index" :class="{ elite: unit.elite }">
              <span class="unit-portrait" :class="{ elite: unit.elite }">
                <img v-if="!missingPortraits.has(portrait(unit.id))" :src="portrait(unit.id)" width="36" height="36" alt=""
                  @error="missingPortraits.add(portrait(unit.id))">
                <span v-else class="report-avatar-fallback" aria-hidden="true">{{ unit.name.slice(0, 1) }}</span>
                <img v-if="unit.elite || unit.evolve === 2" class="elite-badge" :src="ELITE_ICONS.elite2" width="14" height="14" :alt="unit.elite ? '精锐' : '精二'">
                <img v-else-if="unit.evolve === 1" class="elite-badge" :src="ELITE_ICONS.elite1" width="14" height="14" alt="精一">
              </span>
              <b>{{ unit.name }}</b>
              <div v-if="unit.items.length" class="equipment-list">
                <span v-for="item in itemCounts(unit.items)" :key="item.name" class="equipment-chip">
                  <img v-if="EQUIPMENT_ICONS[item.name]" :src="EQUIPMENT_ICONS[item.name]" alt="" @error="($event.target as HTMLImageElement).style.display = 'none'">
                  <span>{{ displayItem(item.name) }}<template v-if="item.count > 1"> ×{{ item.count }}</template></span>
                </span>
              </div>
            </li>
          </ul>
          <p v-else class="muted">无最终阵容记录</p>
        </section>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
#detail {
  width: min(49rem, calc(100% - 1.5rem)); max-height: min(46rem, calc(100dvh - 1.5rem));
  padding: 0; overflow: hidden; border: 1px solid var(--control-line); border-radius: 8px;
  background: var(--panel); color: var(--text); box-shadow: 0 1rem 3.75rem #0005;
  animation: report-enter .14s cubic-bezier(.2, 0, .38, .9) both;
}
#detail[open] { display: flex; flex-direction: column; }
#detail::backdrop { background: rgb(8 14 23 / 66%); }
:global(:root[data-theme='light'] #detail::backdrop) { background: rgb(22 31 47 / 46%); }
@keyframes report-enter { from { transform: translateY(4px); } to { transform: translateY(0); } }
@media (prefers-reduced-motion: reduce) { #detail { animation: none; } }

.report-heading, .report-body { padding-inline: clamp(.8rem, 3.5vw, 1.4rem); }
.report-heading {
  display: flex; align-items: start; justify-content: space-between; gap: .75rem;
  padding-block: .9rem; border-bottom: 1px solid var(--line);
}
.report-title { display: flex; align-items: center; flex-wrap: wrap; gap: .55rem; }
.report-title h2 { font-size: 1.2rem; }
.report-title .chip:hover { transform: none; }
.report-meta { display: flex; flex-wrap: wrap; gap: .1rem .6rem; margin-top: .3rem; color: var(--muted); font-size: .8125rem; }
.report-meta span { white-space: nowrap; }
.report-heading button, .report-error button { min-height: 2.25rem; padding-block: .25rem; }
.report-body { min-height: 0; overflow: auto; overscroll-behavior: contain; padding-block: 1rem 1.2rem; }
.report-content { display: grid; gap: 1rem; }
.report-error { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; color: var(--loss); }

.report-stats {
  grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 1px; margin: 0; overflow: hidden;
  border: 1px solid var(--line); border-radius: 5px; background: var(--line);
}
.report-stats > div { min-width: 0; border: 0; border-radius: 0; padding: .55rem .65rem; background: var(--inset); }
.report-stats dt, .report-setup dt { color: var(--muted); font-size: .75rem; }
.report-stats dd { font: 700 1.04rem/1.4 var(--numbers); overflow-wrap: anywhere; }
.report-setup { display: flex; flex-wrap: wrap; gap: .45rem 1.6rem; }
.report-setup > div, .report-setup dd { display: flex; gap: .4rem; align-items: center; }
.report-setup dd { font-size: .875rem; font-weight: 650; }
.report-setup img { object-fit: contain; }

.report-breakdown { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 1rem; }
.report-section { display: grid; gap: .45rem; align-content: start; min-width: 0; border-top: 1px solid var(--line); padding-top: .6rem; }
.report-section h3 small { margin-left: .35rem; font-weight: 400; }
.report-section :is(.bond-grid, .boss-grid, .squad) { margin-top: 0; }
.report-section .squad { grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr)); }
.report-section .squad li { align-content: start; }
.report-section .squad li > b { min-width: 0; overflow-wrap: anywhere; }
.report-section .equipment-list { flex-basis: 100%; }
.report-avatar-fallback {
  display: inline-grid; place-items: center; flex: none; width: 36px; aspect-ratio: 1;
  border-radius: 4px; color: var(--muted); background: var(--panel);
}
.report-avatar-fallback--small { width: 24px; background: var(--inset); }

@media (max-width: 660px) { .report-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 460px) { .report-breakdown { grid-template-columns: minmax(0, 1fr); } }
</style>
