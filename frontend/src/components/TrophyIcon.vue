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
    alt="" @error="failed = source">
  <NIcon v-else class="trophy-icon trophy-icon--generic" :component="TrophyOutline" :size="size" aria-hidden="true" />
</template>

<style scoped>
/* 奖杯原画是透明底的橙色徽记 + 白色外发光，直接放在面板上，不垫底色；
   亮色主题下白描边会融进浅底，补一圈很淡的阴影把轮廓勾出来。 */
.trophy-icon { flex: none; }
.trophy-icon--art { object-fit: contain; }
:global(:root[data-theme='light'] .trophy-icon--art) {
  filter: drop-shadow(0 0 .6px rgb(60 36 10 / .55)) drop-shadow(0 1px 1px rgb(60 36 10 / .18));
}
.trophy-icon--generic { color: var(--muted); }
</style>
