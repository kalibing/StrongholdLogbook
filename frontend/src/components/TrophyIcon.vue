<script setup lang="ts">
import { computed, ref } from 'vue'
import { NIcon } from 'naive-ui'
import { TrophyOutline } from '@vicons/ionicons5'
import { TROPHY_ICONS } from '../assets'
import type { TrophyBadge } from '../models'

const props = defineProps<{ badge?: TrophyBadge | null; size: number; total?: number | null }>()
const failed = ref('')

/** PRTS「联合成就奖杯与成就」：累计奖杯 0 / 10 / 30 / 60 / 100 / 150 / 200 / 300+ 依次对应 1–8 级。 */
const THRESHOLDS = [0, 10, 30, 60, 100, 150, 200, 300]
function levelFor(total: number): number {
  return THRESHOLDS.filter(threshold => total >= threshold).length || 1
}

const source = computed(() => {
  const id = props.badge?.icon ?? ''
  if (Object.hasOwn(TROPHY_ICONS, id)) return TROPHY_ICONS[id]
  // 优先用成就档案给的等级；没绑定时按累计奖杯数推算；都没有就用第一级奖杯图。
  const level = props.badge?.level ?? (props.total != null ? levelFor(props.total) : 1)
  return TROPHY_ICONS[`trophy_level${level}_icon`] ?? TROPHY_ICONS.trophy_level1_icon
})
</script>

<template>
  <img v-if="source && failed !== source" class="trophy-icon trophy-icon--art" :src="source" :width="size" :height="size"
    :style="{ padding: `${Math.round(size * .12)}px` }" alt="" @error="failed = source">
  <NIcon v-else class="trophy-icon trophy-icon--generic" :component="TrophyOutline" :size="size" aria-hidden="true" />
</template>

<style scoped>
/* 奖杯原画是按游戏里的深色底画的（橙色 + 白描边），直接放在面板上会发虚；
   垫一块方形底板，亮色主题下也用深色底，白描边才看得清。总尺寸不变，内边距把图收进去。 */
.trophy-icon { flex: none; }
.trophy-icon--art {
  box-sizing: border-box; object-fit: contain;
  border: 1px solid color-mix(in srgb, var(--hud) 22%, var(--line)); border-radius: var(--radius);
  background: radial-gradient(circle at 50% 60%, color-mix(in srgb, #f2a046 16%, transparent), transparent 70%), var(--raised);
}
:global(:root[data-theme='light'] .trophy-icon--art) { border-color: #2a3638; background-color: #1b2325; }
.trophy-icon--generic { color: var(--muted); }
</style>
