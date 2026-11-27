<script setup lang="ts">
import { computed } from 'vue'
import { BOSS_ICONS, BOSS_MARKS } from '../assets'

const props = withDefaults(defineProps<{ name: string; size?: number; hidden?: boolean }>(), { size: 20 })
const hiddenSuffix = /\s*[（(]隐藏[）)]$/
const isHidden = computed(() => props.hidden || hiddenSuffix.test(props.name))
const label = computed(() => props.name.replace(hiddenSuffix, ''))
</script>

<template>
  <span class="boss-label" :class="{ 'boss-label--hidden': isHidden }">
    <img :src="BOSS_ICONS[name] ?? BOSS_MARKS.normal" :width="size" :height="size" alt=""
      @error="($event.target as HTMLImageElement).style.display = 'none'">
    <img v-if="isHidden" class="boss-label-mark" :src="BOSS_MARKS.hidden" :width="Math.round(size * .65)"
      :height="Math.round(size * .65)" alt="隐藏首领" title="隐藏首领">
    <span>{{ label }}</span>
  </span>
</template>

<style scoped>
.boss-label { display: inline-flex; align-items: center; gap: .3em; min-width: 0; }
.boss-label img { flex: none; object-fit: contain; }
.boss-label--hidden { color: var(--accent); }
.boss-label-mark { margin-inline-start: .04em; }
.boss-label span { overflow-wrap: anywhere; }
</style>
