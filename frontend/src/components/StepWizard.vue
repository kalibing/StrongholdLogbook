<script setup lang="ts">
// 分步引导：顶部进度条（编号方块 + 步骤名，已完成显示 ✓ 并可点回去），下面只显示当前一步，
// 底部是上一步 / 下一步。绑定成就和数据导入共用。
import { computed } from 'vue'
import { NButton } from 'naive-ui'

const props = withDefaults(defineProps<{
  steps: string[]
  /** 每一步「下一步」按钮的文字；不给就用「下一步」。 */
  nextLabels?: (string | undefined)[]
  /** 为 true 时当前步不能往下走（比如还没填好）。 */
  blocked?: boolean
}>(), { nextLabels: () => [], blocked: false })
const current = defineModel<number>({ required: true })
const last = computed(() => props.steps.length - 1)

function go(index: number) {
  if (index < 0 || index > last.value) return
  current.value = index
}
</script>

<template>
  <div class="wizard">
    <ol class="wizard-rail">
      <li v-for="(title, index) in steps" :key="title" :data-state="index < current ? 'done' : index === current ? 'current' : 'todo'">
        <button type="button" class="wizard-rail-step" :disabled="index > current" :aria-current="index === current ? 'step' : undefined"
          @click="go(index)">
          <span class="wizard-no" aria-hidden="true">{{ index < current ? '✓' : index + 1 }}</span>
          <span class="wizard-title">{{ title }}</span>
        </button>
      </li>
    </ol>

    <div class="wizard-body">
      <Transition name="wizard" mode="out-in">
        <div :key="current" class="wizard-pane">
          <slot :name="`step-${current}`" />
        </div>
      </Transition>
    </div>

    <footer class="wizard-foot">
      <NButton v-if="current > 0" secondary @click="go(current - 1)">上一步</NButton>
      <span class="wizard-count">{{ current + 1 }} / {{ steps.length }}</span>
      <slot name="actions" :step="current" />
      <NButton v-if="current < last" type="primary" :disabled="blocked" @click="go(current + 1)">
        {{ nextLabels[current] ?? '下一步' }}
      </NButton>
    </footer>
  </div>
</template>

<style scoped>
.wizard { display: grid; gap: 1.1rem; }

/* 进度条：编号 → 步骤名 → 一条伸到下一步的细线；走过的线变主色。线跟在文字后面，不会压到字上。 */
.wizard-rail { display: flex; margin: 0; padding: 0; list-style: none; }
.wizard-rail li { display: flex; flex: 1; align-items: center; min-width: 0; }
.wizard-rail li:last-child { flex: none; }
.wizard-rail li:not(:last-child)::after {
  content: ""; flex: 1; min-width: 1.5rem; height: 1px; margin-inline: .8rem; background: var(--line-strong);
}
.wizard-rail li[data-state='done']::after { background: var(--accent); }
.wizard-rail-step {
  display: flex; flex: none; align-items: center; gap: .6rem; max-width: 100%; min-height: 0; padding: 0; justify-content: flex-start;
  border: 0; background: transparent; color: var(--muted); text-align: left; white-space: nowrap;
}
.wizard-rail-step:hover:not(:disabled) { border: 0; color: var(--text); }
.wizard-rail-step:disabled { opacity: 1; cursor: default; }
.wizard-no {
  display: grid; place-items: center; flex: none; width: 30px; height: 30px;
  border: 1px solid var(--line-strong); border-radius: var(--radius); background: var(--inset);
  font: 700 .95rem/1 var(--numbers);
}
.wizard-title { overflow: hidden; text-overflow: ellipsis; font-size: .875rem; letter-spacing: .04em; }
[data-state='current'] .wizard-rail-step { color: var(--text); font-weight: 650; }
[data-state='current'] .wizard-no { border-color: var(--accent); background: var(--accent); color: var(--accent-ink); }
[data-state='done'] .wizard-rail-step { color: var(--text-2); }
[data-state='done'] .wizard-no { border-color: var(--accent); color: var(--accent); }

.wizard-body { min-height: 9rem; padding: 1.1rem 1.2rem; border: 1px solid var(--line); border-radius: var(--radius); background: var(--inset); }
.wizard-pane { display: grid; gap: .75rem; }

.wizard-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: .6rem; }
.wizard-count { margin-right: auto; color: var(--muted); font: 600 .95rem/1 var(--numbers); letter-spacing: .08em; order: -1; }

@media (prefers-reduced-motion: no-preference) {
  .wizard-enter-active, .wizard-leave-active { transition: opacity .16s ease, transform .18s cubic-bezier(.2, .7, .3, 1); }
  .wizard-enter-from { opacity: 0; transform: translateX(10px); }
  .wizard-leave-to { opacity: 0; transform: translateX(-6px); }
}
@media (max-width: 620px) {
  .wizard-title { display: none; }
  [data-state='current'] .wizard-title { display: block; }
}
</style>
