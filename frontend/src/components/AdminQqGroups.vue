<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NCheckbox, NCheckboxGroup, NInput, NSelect, useMessage } from 'naive-ui'
import { api, message, send, useResource } from '../api'

type Source = 'ak' | 'bili'
interface QqGroup {
  group_openid: string
  group_number: string | null
  updated_at: string
  sources: Source[]
}

const revision = ref(0)
const { data, pending, error, refresh } = useResource<{ enabled: boolean; items: QqGroup[] }>(
  ref('/admin/qq-groups'), revision, true,
)
const timeFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
})
const options = computed(() => (data.value?.items ?? []).map(group => ({
  value: group.group_openid,
  label: group.group_number
    ? '群 ' + group.group_number
    : 'OpenID …' + group.group_openid.slice(-8) + ' · ' + timeFormat.format(new Date(group.updated_at)),
})))
const selected = ref<string | null>(null)
const groupNumber = ref('')
const sources = ref<Source[]>([])
const saving = ref(false)
const toast = useMessage()

function chooseGroup(openid: string) {
  const group = data.value?.items.find(item => item.group_openid === openid)
  if (!group) return
  selected.value = openid
  groupNumber.value = group.group_number ?? ''
  sources.value = [...group.sources]
}

async function save() {
  if (!selected.value) return
  const number = groupNumber.value.trim()
  if (number && !/^[0-9]{1,20}$/.test(number)) {
    toast.error('QQ群号须为数字。')
    return
  }
  saving.value = true
  try {
    await api('/admin/qq-groups/' + encodeURIComponent(selected.value), send('PUT', {
      group_number: number || null,
      sources: sources.value,
    }))
    toast.success('已保存')
    refresh()
  } catch (reason) {
    toast.error(message(reason))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="panel qq-groups" aria-labelledby="qq-groups-title">
    <div class="section-heading"><h2 id="qq-groups-title">QQ 群推送</h2></div>
    <p v-if="error" class="load-message" role="alert">{{ error }}</p>
    <p v-else-if="data && !data.enabled" class="muted">站点尚未配置 QQ 机器人。</p>
    <p v-else-if="pending && !data" class="muted" role="status">正在加载…</p>
    <template v-else>
      <p class="muted">新群先 @机器人发一次消息，再刷新群列表。群号用于在这里识别推送目标。</p>
      <form class="qq-group-form" @submit.prevent="save">
        <div class="qq-group-actions">
          <NSelect :value="selected" :options="options" placeholder="选择机器人已识别的群"
            aria-label="推送目标群" :disabled="saving" @update:value="chooseGroup" />
          <NButton secondary :loading="pending" :disabled="saving" @click="refresh">刷新群列表</NButton>
        </div>
        <template v-if="selected">
          <NInput v-model:value="groupNumber" placeholder="QQ 群号" aria-label="QQ 群号" :maxlength="20"
            :disabled="saving" :input-props="{ inputmode: 'numeric' }" />
          <NCheckboxGroup v-model:value="sources" :disabled="saving" aria-label="群推送内容">
            <div class="qq-group-actions">
              <NCheckbox value="ak">明日方舟公告</NCheckbox>
              <NCheckbox value="bili">B 站官号动态</NCheckbox>
            </div>
          </NCheckboxGroup>
          <div class="qq-group-actions">
            <NButton type="primary" attr-type="submit" :loading="saving">保存</NButton>
          </div>
        </template>
      </form>
    </template>
  </section>
</template>

<style scoped>
.qq-groups { display: grid; gap: .75rem; padding: 1.25rem 1.5rem; }
.qq-group-form { display: grid; gap: .75rem; max-width: 40rem; }
.qq-group-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .65rem; }
.qq-group-actions .n-select { flex: 1 1 14rem; min-width: 0; }
.qq-groups :is(.muted, .load-message) { margin: 0; }
@media (max-width: 640px) {
  .qq-groups { padding: 1rem; }
}
</style>
