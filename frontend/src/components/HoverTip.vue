<script setup lang="ts">
import { onBeforeUnmount, ref, useId } from 'vue'

const props = withDefaults(defineProps<{ as?: 'span' | 'td'; text?: string; placement?: 'top' | 'bottom'; focusable?: boolean }>(), {
  as: 'span',
  text: '',
  placement: 'top',
  // 放在本身可聚焦的行里时关掉，免得一行要按两次 Tab。
  focusable: true,
})

const shown = ref(false)
const position = ref({ left: 0, top: 0 })
const trigger = ref<HTMLElement | null>(null)
const tipId = useId()
let timer: number | undefined

function show() {
  if (!props.text) return
  window.clearTimeout(timer)
  // 稍等一下再出，鼠标扫过表格时不会满屏气泡
  timer = window.setTimeout(() => {
    const rect = trigger.value?.getBoundingClientRect()
    if (!rect) return
    position.value = {
      left: rect.left + rect.width / 2,
      top: props.placement === 'top' ? rect.top - 6 : rect.bottom + 6,
    }
    shown.value = true
  }, 140)
}

function hide() {
  window.clearTimeout(timer)
  shown.value = false
}

onBeforeUnmount(() => window.clearTimeout(timer))
</script>

<template>
  <component :is="as" ref="trigger" class="hover-tip" :tabindex="text && focusable ? 0 : undefined"
    :aria-describedby="shown ? tipId : undefined" @mouseenter="show" @mouseleave="hide"
    @focusin="show" @focusout="hide" @keydown.escape="hide">
    <slot />
    <Teleport to="body">
      <Transition name="hover-tip">
        <span v-if="shown" :id="tipId" class="hover-tip-bubble" :data-placement="placement" role="tooltip"
          :style="{ left: position.left + 'px', top: position.top + 'px' }">{{ text }}</span>
      </Transition>
    </Teleport>
  </component>
</template>

<style scoped>
@media (prefers-reduced-motion: no-preference) {
  .hover-tip-enter-active { transition: opacity 150ms ease-out, translate 150ms cubic-bezier(.2, .7, .3, 1); }
  .hover-tip-enter-from { opacity: 0; translate: 0 4px; }
  .hover-tip-enter-from[data-placement='bottom'] { translate: 0 -4px; }
  .hover-tip-leave-active { transition: opacity 100ms ease-in; }
  .hover-tip-leave-to { opacity: 0; }
}
</style>
