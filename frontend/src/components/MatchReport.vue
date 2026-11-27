<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { BOND_ICONS, bossName } from '../assets'
import BossLabel from './BossLabel.vue'
import { strategyIcon, strategyOf, unitOf } from '../bands'
import { avatarFor, loadDirectory } from '../directory'
import { resolveEquipment } from '../equipment'
import { dateTime, difficultyLabel, number, resultLabel } from '../format'
import { portrait } from '../icons'
import type { MatchDetail } from '../models'

const props = defineProps<{ detail: MatchDetail | null; pending?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; retry: [] }>()

const dialog = ref<HTMLDialogElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const names = ref(new Map<string, string>())
const missingPortraits = reactive(new Set<string>())
// 发起干员 = 策略对应的分队干员（band 映射）；initiator 为「本人 / 队友」时只表示由谁发起，不展示。
const PARTIES = ['本人', '队友']
const initiatorName = computed(() => unitOf(props.detail?.strategy)
  || (props.detail?.initiator && !PARTIES.includes(props.detail.initiator) ? props.detail.initiator : ''))
const initiatorAvatar = computed(() => avatarFor(names.value, initiatorName.value || null))
const strategy = computed(() => strategyOf(props.detail?.strategy))
const strategyArt = computed(() => strategyIcon(props.detail?.strategy))
const itemCounts = (items: string[]) => {
  const counts = new Map<string, number>()
  for (const item of items) counts.set(item, (counts.get(item) ?? 0) + 1)
  return [...counts].map(([id, count]) => ({ id, count, ...resolveEquipment(id) }))
}
const squad = computed(() => (props.detail?.squad ?? []).map((unit, index) => ({
  ...unit,
  key: `${unit.id}:${index}`,
  equipment: itemCounts(unit.items),
})))
const defeatedBosses = computed(() => (props.detail?.bosses ?? []).map(bossName))
const activeBonds = computed(() => (props.detail?.bonds ?? []).filter(bond => bond.layers > 0))
const totalLayers = computed(() => activeBonds.value.reduce((sum, bond) => sum + bond.layers, 0))
/** 盟约行里的层数条：按本局最高的盟约归一，一眼看出主次。 */
const maxLayers = computed(() => Math.max(1, ...activeBonds.value.map(bond => bond.layers)))
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
        <dl v-if="strategy || initiatorName" class="report-setup">
          <div v-if="strategy">
            <dt>开局策略</dt>
            <dd>
              <img v-if="strategyArt" :src="strategyArt" width="30" height="30" alt="">
              {{ strategy }}
            </dd>
          </div>
          <div v-if="initiatorName">
            <!-- 只写干员名：标签文字和头像缺图时的首字占位都不显示，读屏仍保留「发起干员」。 -->
            <dt class="sr-only">发起干员</dt>
            <dd>
              <img v-if="initiatorAvatar && !missingPortraits.has(initiatorAvatar)" :src="initiatorAvatar" width="24" height="24" alt=""
                @error="missingPortraits.add(initiatorAvatar)">
              {{ initiatorName }}
            </dd>
          </div>
        </dl>

        <dl class="report-stats">
          <div><dt>回合</dt><dd>{{ number(detail.rounds) }}</dd></div>
          <div><dt>击杀</dt><dd>{{ number(detail.kills) }}</dd></div>
          <div><dt>金币花费</dt><dd>{{ number(detail.coins) }}</dd></div>
          <div><dt>同步次数</dt><dd>{{ number(detail.sync_count) }}</dd></div>
          <div><dt>时长</dt><dd>{{ duration }}</dd></div>
          <div><dt>获得奖杯</dt><dd :class="{ 'report-gain': (detail.trophies ?? 0) > 0 }">{{ number(detail.trophies) }}</dd></div>
        </dl>

        <div class="report-breakdown">
          <section class="report-section">
            <h3>盟约 <small>{{ activeBonds.length }} 种 · {{ totalLayers }} 层</small></h3>
            <ul v-if="activeBonds.length" class="report-list report-bonds">
              <li v-for="bond in activeBonds" :key="bond.name">
                <span class="bond-label">
                  <img v-if="BOND_ICONS[bond.name]" :src="BOND_ICONS[bond.name]" width="22" height="22" alt="" @error="($event.target as HTMLImageElement).style.display = 'none'">
                  <span>{{ bond.name }}</span>
                </span>
                <span class="report-bond-bar" aria-hidden="true"><i :style="{ width: `${bond.layers / maxLayers * 100}%` }"></i></span>
                <b>{{ bond.layers }}<small>层</small></b>
              </li>
            </ul>
            <p v-else class="muted">无盟约记录</p>
          </section>

          <section class="report-section">
            <h3>已击杀首领 <small v-if="defeatedBosses.length">{{ defeatedBosses.length }} 个</small></h3>
            <ul v-if="defeatedBosses.length" class="report-list report-bosses">
              <li v-for="(boss, index) in defeatedBosses" :key="index">
                <BossLabel :name="boss" :size="30" />
              </li>
            </ul>
            <p v-else class="muted">无首领击杀记录</p>
          </section>
        </div>

        <section class="report-section">
          <h3>最终阵容</h3>
          <ul v-if="squad.length" class="squad">
            <li v-for="unit in squad" :key="unit.key" class="squad-card"
              :class="{ 'squad-card--elite': unit.elite }" :title="unit.elite ? '精锐' : undefined">
              <span class="unit-portrait">
                <img v-if="!missingPortraits.has(portrait(unit.id))" :src="portrait(unit.id)" width="52" height="52" alt=""
                  @error="missingPortraits.add(portrait(unit.id))">
                <span v-else class="report-avatar-fallback" aria-hidden="true">{{ unit.name.slice(0, 1) }}</span>
              </span>
              <div class="unit-details">
                <div class="unit-heading">
                  <b class="unit-name">{{ unit.name }}<span v-if="unit.elite" class="unit-status">，精锐</span></b>
                </div>
                <div v-if="unit.equipment.length" class="equipment-list">
                  <span v-for="item in unit.equipment"
                    :key="item.id" class="equipment-chip"
                    :class="{ 'equipment-chip--advanced': item.advanced }" :title="item.advanced ? '进阶装备' : undefined">
                    <img v-if="item.icon" :src="item.icon" :alt="item.advanced ? '进阶' : ''" @error="($event.target as HTMLImageElement).style.display = 'none'">
                    <span class="equipment-name">{{ item.name }}</span>
                    <span v-if="item.count > 1" class="equipment-count">×{{ item.count }}</span>
                  </span>
                </div>
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
  --elite-border: #e1a744;
  width: min(49rem, calc(100% - 1.5rem)); max-height: min(46rem, calc(100dvh - 1.5rem));
  padding: 0; overflow: hidden; border: 1px solid var(--control-line); border-radius: var(--radius);
  background: var(--panel); color: var(--text); box-shadow: 0 1rem 3.75rem #0005;
  animation: report-enter .14s cubic-bezier(.2, 0, .38, .9) both;
}
#detail[open] { display: flex; flex-direction: column; }
#detail::backdrop { background: rgb(6 11 9 / 66%); }
:global(:root[data-theme='light'] #detail) { --elite-border: #a86b20; }
:global(:root[data-theme='light'] #detail::backdrop) { background: rgb(20 32 26 / 46%); }
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
.report-meta { display: flex; flex-wrap: wrap; gap: .1rem .6rem; margin-top: .3rem; color: var(--muted); font-size: .875rem; }
.report-meta span { white-space: nowrap; }
.report-heading button, .report-error button { min-height: 2.25rem; padding-block: .25rem; }
.report-body { min-height: 0; overflow: auto; overscroll-behavior: contain; padding-block: 1rem 1.2rem; }
.report-content { display: grid; gap: 1rem; }
.report-error { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; color: var(--loss); }

.report-stats {
  grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 1px; margin: 0; overflow: hidden;
  border: 1px solid var(--line); border-radius: var(--radius); background: var(--line);
}
.report-stats > div { min-width: 0; border: 0; border-radius: 0; padding: .55rem .65rem; background: var(--inset); }
.report-stats dt, .report-setup dt { color: var(--muted); font-size: .8125rem; }
.report-stats dd { font: 700 1.04rem/1.4 var(--numbers); overflow-wrap: anywhere; }
#detail .report-stats dd.report-gain { color: var(--win); }
.report-setup { display: flex; flex-wrap: wrap; gap: .45rem 1.4rem; padding: .5rem .75rem; border: 1px solid var(--line); border-radius: var(--radius); background: var(--inset); }
.report-setup > div, .report-setup dd { display: flex; gap: .4rem; align-items: center; }
.report-setup dt { font-size: .875rem; }
.report-setup dd { font-size: 1rem; font-weight: 700; }
.report-setup img { object-fit: contain; }

.report-breakdown { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.report-section { display: grid; gap: .45rem; align-content: start; min-width: 0; border-top: 1px solid var(--line); padding-top: .6rem; }
.report-section h3 small { margin-left: .35rem; font-weight: 400; }
.report-section .squad { margin-top: 0; }
/* 盟约、首领都用整行列表：两栏等宽、行高一致，不再是参差不齐的小卡片。 */
.report-list { display: grid; gap: 1px; margin: 0; padding: 0; list-style: none; border: 1px solid var(--line); border-radius: var(--radius); background: var(--line); overflow: hidden; }
.report-list li { display: flex; align-items: center; gap: .6rem; min-height: 2.6rem; padding: .35rem .7rem; background: var(--inset); }
.report-bonds li { display: grid; grid-template-columns: minmax(5.5rem, auto) minmax(2rem, 1fr) auto; }
.report-bonds .bond-label img { width: 22px; height: 22px; }
.report-bond-bar { height: 4px; border-radius: 2px; background: color-mix(in srgb, var(--text) 8%, transparent); overflow: hidden; }
.report-bond-bar i { display: block; height: 100%; border-radius: inherit; background: var(--accent); }
.report-bonds b { min-width: 2.6rem; color: var(--text); font: 700 1.05rem/1 var(--numbers); text-align: right; white-space: nowrap; }
.report-bonds b small { margin-left: .15rem; color: var(--muted); font: 400 .8125rem system-ui, sans-serif; }
.report-bosses li { font-weight: 650; }
.report-section .squad {
  --unit-portrait-size: clamp(2.65rem, 3.75vw, 3.25rem);
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .5rem;
}
.report-section .squad .squad-card {
  display: grid; grid-template-columns: var(--unit-portrait-size) minmax(0, 1fr); align-items: center;
  gap: .5rem; min-width: 0;
  padding: .45rem .5rem; border-radius: var(--radius); background: var(--inset);
}
.report-section .squad .squad-card--elite {
  border-color: color-mix(in srgb, var(--elite-border) 65%, var(--line));
  background: linear-gradient(100deg, color-mix(in srgb, var(--elite-border) 8%, var(--inset)), var(--inset) 72%);
}
.unit-details { display: grid; gap: .28rem; min-width: 0; }
.unit-heading { display: flex; align-items: center; gap: .45rem; min-width: 0; }
.unit-portrait { display: grid; place-items: center; width: 100%; aspect-ratio: 1; border-radius: var(--radius); background: var(--chart-label); overflow: hidden; }
.unit-portrait img, .unit-portrait .report-avatar-fallback { width: 100%; height: 100%; }
.unit-status { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.unit-name, .equipment-name { min-width: 0; overflow-wrap: anywhere; }
.unit-name { flex: 1; font-size: .88rem; line-height: 1.25; }
.squad-card .equipment-list { display: grid; gap: .3rem; }
.report-section .equipment-chip {
  gap: .28rem; padding: 0; background: transparent;
  color: color-mix(in srgb, var(--text) 78%, var(--muted)); font-size: .8125rem; line-height: 1.22;
}
.report-section .equipment-chip img { width: 17px; height: 17px; flex: none; object-fit: contain; border-radius: 2px; background: var(--chart-label); }
.equipment-count { flex: none; margin-inline-start: auto; font: 650 .8125rem var(--numbers); color: var(--muted); }
.report-section .equipment-chip--advanced img { outline: 1.5px solid #e1a744; outline-offset: 1px; }
.report-avatar-fallback {
  display: inline-grid; place-items: center; flex: none; width: 36px; aspect-ratio: 1;
  border-radius: var(--radius); color: var(--muted); background: var(--panel);
}

@media (max-width: 660px) {
  .report-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .report-section .squad { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 460px) { .report-breakdown { grid-template-columns: minmax(0, 1fr); } }
</style>
