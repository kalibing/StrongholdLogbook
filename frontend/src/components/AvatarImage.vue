<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  src?: string | null
  fallbackSrc?: string | null
  name?: string | null
  size?: number
}>(), { size: 36 })

const attempt = ref(0)
const imageUrl = computed(() => [props.src, props.fallbackSrc].filter(Boolean)[attempt.value])
watch(() => [props.src, props.fallbackSrc], () => { attempt.value = 0 }, { flush: 'sync' })
</script>

<template>
  <span class="avatar-image" :style="{ '--avatar-size': size + 'px' }" aria-hidden="true">
    <img v-if="imageUrl" :key="imageUrl" :src="imageUrl" alt="" @error="attempt++">
    <span v-else class="avatar-initial">{{ name?.trim().slice(0, 1) || '—' }}</span>
  </span>
</template>

<style scoped>
.avatar-image {
  display: inline-grid; flex: none; width: var(--avatar-size); aspect-ratio: 1; place-items: center;
  overflow: hidden; border-radius: 4px;
}
.avatar-image img { display: block; width: 100%; height: 100%; object-fit: cover; }
.avatar-initial {
  display: grid; width: 100%; height: 100%; place-items: center;
  color: var(--muted); background: var(--inset); font-weight: 650;
}
</style>
