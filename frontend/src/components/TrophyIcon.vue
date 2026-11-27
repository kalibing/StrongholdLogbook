<script setup lang="ts">
import { computed, ref } from 'vue'
import { NIcon } from 'naive-ui'
import { TrophyOutline } from '@vicons/ionicons5'
import { TROPHY_ICONS } from '../assets'
import type { TrophyBadge } from '../models'

const props = defineProps<{ badge?: TrophyBadge | null; size: number }>()
const failed = ref('')
const source = computed(() => {
  const id = props.badge?.icon ?? ''
  const levelId = `trophy_level${props.badge?.level}_icon`
  return Object.hasOwn(TROPHY_ICONS, id) ? TROPHY_ICONS[id] : TROPHY_ICONS[levelId]
})
</script>

<template>
  <img v-if="source && failed !== source" class="trophy-icon" :src="source" :width="size" :height="size" alt="" @error="failed = source">
  <NIcon v-else class="trophy-icon trophy-icon--generic" :component="TrophyOutline" :size="size" aria-hidden="true" />
</template>

<style scoped>
.trophy-icon { flex: none; object-fit: contain; }
.trophy-icon--generic { color: var(--muted); }
</style>
