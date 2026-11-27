<script setup lang="ts">
import { NPagination, type SelectProps } from 'naive-ui'

defineProps<{ page: number; pageSize: number; total: number; disabled?: boolean }>()
defineEmits<{ 'update:page': [value: number]; 'update:pageSize': [value: number] }>()
const sizes = [10, 20, 50]
const sizePickerProps: SelectProps & { 'aria-label': string } = { 'aria-label': '每页条数' }
</script>

<template>
  <nav class="paging list-pagination" aria-label="列表分页">
    <NPagination :page="page" :item-count="total" :page-slot="5" :disabled="disabled"
      show-size-picker :page-size="pageSize" :page-sizes="sizes" :select-props="sizePickerProps"
      @update:page="$emit('update:page', $event)" @update:page-size="$emit('update:pageSize', $event)" />
  </nav>
</template>

<style scoped>
.list-pagination :deep(.n-pagination) { flex-wrap: wrap; justify-content: flex-end; gap: .55rem; }
.list-pagination :deep(.n-pagination > *) { margin: 0; }
.list-pagination :deep(.n-pagination > .n-select) { margin-inline-start: .45rem; }
@media (max-width: 440px) {
  .list-pagination { padding-inline: .65rem; }
  .list-pagination :deep(.n-pagination) { gap: .32rem; }
}
</style>
