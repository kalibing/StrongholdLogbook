<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BOND_ICONS, BOSS_ICONS, EQUIPMENT_ICONS, STRATEGY_ICONS } from '../assets'
import { dateTime, difficultyLabel, number, resultLabel } from '../format'
import { portrait } from '../icons'
import type { MatchDetail } from '../models'

const props = defineProps<{ detail: MatchDetail | null; pending?: boolean; error?: string }>()
const emit = defineEmits<{ close: [] }>()

const dialog = ref<HTMLDialogElement | null>(null)
const totalLayers = computed(() => props.detail?.bonds.reduce((sum, bond) => sum + bond.layers, 0) ?? 0)
const duration = computed(() => {
  const seconds = props.detail?.duration_seconds
  if (!seconds) return '—'
  return Math.floor(seconds / 60) + ' 分 ' + seconds % 60 + ' 秒'
})
const meta = computed(() => props.detail
  ? [dateTime(props.detail.played_at), resultLabel(props.detail.result), props.detail.play, difficultyLabel(props.detail.difficulty)].join(' · ')
  : '正在读取战报…')

function close() {
  dialog.value?.close()
}

onMounted(() => {
  dialog.value?.showModal()
})
</script>

<template>
  <dialog ref="dialog" id="detail" aria-labelledby="detail-title" @close="emit('close')">
    <div class="split dialog-heading">
      <h2 id="detail-title">单局战报</h2>
      <button type="button" @click="close">关闭</button>
    </div>

    <p v-if="pending" class="muted" role="status">正在读取战报…</p>
    <p v-else-if="error" class="load-message" role="alert">{{ error }}</p>

    <div v-else-if="detail" id="report">
      <p class="report-meta">{{ meta }}</p>

      <div v-if="detail.strategy || detail.initiator" class="strategy-fields">
        <div class="art-card">
          <small>开局策略</small>
          <img v-if="detail.strategy && STRATEGY_ICONS[detail.strategy]" :src="STRATEGY_ICONS[detail.strategy]" alt="">
          <b>{{ detail.strategy ?? '—' }}</b>
        </div>
        <div class="art-card">
          <small>发起者</small>
          <b>{{ detail.initiator ?? '—' }}</b>
        </div>
      </div>

      <div class="report-stats">
        <div><small>回合</small><b>{{ number(detail.rounds) }}</b></div>
        <div><small>击杀</small><b>{{ number(detail.kills) }}</b></div>
        <div><small>金币花费</small><b>{{ number(detail.coins) }}</b></div>
        <div><small>同步次数</small><b>{{ number(detail.sync_count) }}</b></div>
        <div><small>时长</small><b>{{ duration }}</b></div>
        <div><small>奖杯变化</small><b>{{ number(detail.trophies) }}</b></div>
      </div>

      <h3>盟约 · {{ detail.bonds.length }} 种 / {{ totalLayers }} 层</h3>
      <div v-if="detail.bonds.length" class="bond-grid">
        <div v-for="bond in detail.bonds" :key="bond.name">
          <span class="bond-label">
            <img v-if="BOND_ICONS[bond.name]" :src="BOND_ICONS[bond.name]" width="23" height="23" alt="" @error="($event.target as HTMLImageElement).style.display = 'none'">
            <span>{{ bond.name }}</span>
          </span>
          <b>{{ bond.layers }} 层</b>
        </div>
      </div>
      <p v-else class="muted">无</p>

      <h3>已击杀首领</h3>
      <div v-if="detail.bosses.length" class="boss-grid">
        <div v-for="boss in detail.bosses" :key="boss" class="art-card">
          <img v-if="BOSS_ICONS[boss]" :src="BOSS_ICONS[boss]" width="42" height="42" alt="" @error="($event.target as HTMLImageElement).style.display = 'none'">
          <b>{{ boss }}</b>
        </div>
      </div>
      <p v-else class="muted">无</p>

      <h3>最终阵容</h3>
      <ul v-if="detail.squad.length" class="squad">
        <li v-for="unit in detail.squad" :key="unit.id">
          <img :src="portrait(unit.id)" width="36" height="36" alt="" @error="($event.target as HTMLImageElement).style.display = 'none'">
          <b>{{ unit.name }}</b>
          <div v-if="unit.items.length" class="equipment-list">
            <span v-for="(item, index) in unit.items" :key="index" class="equipment-chip">
              <img v-if="EQUIPMENT_ICONS[item]" :src="EQUIPMENT_ICONS[item]" alt="" @error="($event.target as HTMLImageElement).style.display = 'none'">
              <span>{{ item }}</span>
            </span>
          </div>
        </li>
      </ul>
      <p v-else class="muted">无最终阵容记录</p>
    </div>
  </dialog>
</template>
