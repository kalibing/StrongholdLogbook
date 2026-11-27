<script setup lang="ts">
import { computed } from 'vue'
import { difficultyIcon } from '../assets'

const props = defineProps<{ label: string; size?: number }>()
const icon = computed(() => difficultyIcon(props.label))
const px = computed(() => props.size ?? 18)
</script>

<template>
  <span class="tier-tag">
    <img v-if="icon" :src="icon" :width="px" :height="px" alt="">
    <span>{{ label }}</span>
  </span>
</template>
