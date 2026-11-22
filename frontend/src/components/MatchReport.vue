<script setup lang="ts">
import { computed } from 'vue'
import { dateTime, number, protocolLabel, resultLabel } from '../format'
import type { MatchDetail } from '../models'

const props = defineProps<{ detail: MatchDetail | null; pending?: boolean; error?: string }>()
defineEmits<{ close: [] }>()

const totalLayers = computed(() => props.detail?.bonds.reduce((sum, bond) => sum + bond.layers, 0) ?? 0)
const duration = computed(() => {
  const seconds = props.detail?.duration_seconds
  if (!seconds) return '—'
  const minutes = Math.floor(seconds / 60)
  return minutes ? `${minutes} 分 ${seconds % 60} 秒` : `${seconds} 秒`
})
const bosses = computed(() => props.detail?.bosses ?? [])
</script>

<template>
  <div class="report-backdrop" role="presentation" @click.self="$emit('close')">
    <section class="report" role="dialog" aria-modal="true" aria-labelledby="report-title">
      <header class="report-head">
        <div>
          <p class="eyebrow">{{ detail ? resultLabel(detail.result) + ' · ' + detail.difficulty : '战报' }}</p>
          <h2 id="report-title">{{ detail ? dateTime(detail.played_at) : '正在读取战报…' }}</h2>
        </div>
        <button type="button" class="quiet" @click="$emit('close')">关闭</button>
      </header>

      <p v-if="pending" class="muted" role="status">正在读取战报…</p>
      <p v-else-if="error" class="error" role="alert">{{ error }}</p>

      <template v-else-if="detail">
        <dl class="report-grid">
          <div><dt>协议期</dt><dd>{{ protocolLabel(detail.protocol) }}</dd></div>
          <div><dt>模拟方式</dt><dd>{{ detail.play }}</dd></div>
          <div><dt>难度 / 等级</dt><dd>{{ detail.difficulty }}</dd></div>
          <div><dt>结果</dt><dd><span class="tag" :class="{ loss: detail.result === 'loss' }">{{ resultLabel(detail.result) }}</span></dd></div>
          <div><dt>通过回合</dt><dd>{{ number(detail.rounds) }}</dd></div>
          <div><dt>敌人击杀</dt><dd>{{ number(detail.kills) }}</dd></div>
          <div><dt>金币花费</dt><dd>{{ number(detail.coins) }}</dd></div>
          <div><dt>对局时长</dt><dd>{{ duration }}</dd></div>
          <div><dt>奖杯增益</dt><dd>{{ number(detail.trophies) }}</dd></div>
          <div><dt>同步次数</dt><dd>{{ number(detail.sync_count) }}</dd></div>
          <div><dt>盟约总层数</dt><dd>{{ number(totalLayers) }}</dd></div>
          <div><dt>分队</dt><dd>{{ detail.scenario ?? '—' }}</dd></div>
          <div><dt>开局策略</dt><dd>{{ detail.strategy ?? '—' }}</dd></div>
          <div><dt>策略发起者</dt><dd>{{ detail.initiator ?? '—' }}</dd></div>
        </dl>

        <div class="report-block">
          <h3>盟约结算</h3>
          <div v-if="detail.bonds.length" class="tag-list">
            <span v-for="bond in detail.bonds" :key="bond.name" class="tag neutral">{{ bond.name }} {{ bond.layers }} 层</span>
          </div>
          <p v-else class="muted">本局没有盟约明细。</p>
        </div>

        <div class="report-block">
          <h3>首领</h3>
          <div v-if="bosses.length" class="tag-list">
            <span v-for="boss in bosses" :key="boss" class="tag neutral">{{ boss }}</span>
          </div>
          <p v-else class="muted">本局没有首领记录。</p>
        </div>

        <div class="report-block">
          <h3>最终阵容</h3>
          <div v-if="detail.squad.length" class="squad-grid">
            <article v-for="unit in detail.squad" :key="unit.id" class="unit-card">
              <strong>{{ unit.name }}</strong>
              <div v-if="unit.items.length" class="items">
                <span v-for="item in unit.items" :key="item">{{ item }}</span>
              </div>
              <small v-else class="muted">无装备</small>
            </article>
          </div>
          <p v-else class="muted">本局没有阵容明细。</p>
        </div>
      </template>
    </section>
  </div>
</template>
