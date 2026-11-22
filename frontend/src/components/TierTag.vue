<script setup lang="ts">
import { computed } from 'vue'
import { DIFFICULTY_ICONS } from '../assets'

const props = defineProps<{ label: string; size?: number }>()
const icon = computed(() => DIFFICULTY_ICONS[props.label])
const px = computed(() => props.size ?? 18)
</script>

<template>
  <span class="tier-tag">
    <img v-if="icon" :src="icon" :width="px" :height="px" alt="">
    <span>{{ label }}</span>
  </span>
</template>
