<script setup lang="ts">
defineProps<{ pending?: boolean; error?: string; empty?: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div v-if="pending" class="feedback panel" role="status">正在读取数据…</div>
  <div v-else-if="error" class="feedback panel" role="alert">
    <p>{{ error }}</p>
    <button type="button" @click="$emit('retry')">重试</button>
  </div>
  <div v-else-if="empty" class="feedback panel" role="status"><p>{{ empty }}</p><slot /></div>
</template>
