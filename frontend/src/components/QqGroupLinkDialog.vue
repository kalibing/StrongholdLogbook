<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton, NModal } from 'naive-ui'
import { api, message, post } from '../api'

// QQ 群成员第一次在群里 @机器人 查日报时，机器人私聊发来一次性关联链接（#qq-group=令牌）。
// 这里展示要关联的群成员，用户主动确认后才把这个群身份关联到当前账号：
// 自动关联的话，别人把自己的链接发给你、你点开就会把他的群身份挂到你的账号上。
const props = defineProps<{ token: string }>()
const emit = defineEmits<{ closed: [] }>()

type Preview = { nickname: string, group_number: string | null }
/** loading：读取链接；confirm：等待确认；done：已关联；failed：链接无效等，只剩提示。 */
const stage = ref<'loading' | 'confirm' | 'done' | 'failed'>('loading')
const preview = ref<Preview | null>(null)
const busy = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    preview.value = await api<Preview>('/qq-group-link/preview', post({ token: props.token }))
    stage.value = 'confirm'
  } catch (reason) {
    error.value = message(reason)
    stage.value = 'failed'
  }
})

async function confirm() {
  busy.value = true
  error.value = ''
  try {
    await api<void>('/qq-group-link/confirm', post({ token: props.token }))
    stage.value = 'done'
  } catch (reason) {
    error.value = message(reason)
    stage.value = 'failed'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <NModal :show="stage !== 'loading'" preset="card" class="set-password-modal" :bordered="false" :mask-closable="false"
    :title="stage === 'done' ? '已关联 QQ 群身份' : stage === 'failed' ? '无法关联 QQ 群身份' : '关联 QQ 群身份'"
    @update:show="value => { if (!value) emit('closed') }">
    <template v-if="stage === 'confirm' && preview">
      <p class="set-password-note">
        将把群成员<b>「{{ preview.nickname || '（未取到群昵称）' }}」</b><template v-if="preview.group_number">在群
        <code>{{ preview.group_number }}</code></template>的身份关联到你的账号。之后他在群里 @机器人 发「日报」，会显示你的昨日战报，发「战绩」会显示你最近 10 局的战绩。
      </p>
      <p class="muted set-password-note">不是你本人在群里请求的，请不要确认。在群里 @机器人 发「解绑」可以随时解除。</p>
      <div class="set-password-actions">
        <NButton secondary :disabled="busy" @click="emit('closed')">取消</NButton>
        <NButton type="primary" :loading="busy" @click="confirm">确认关联</NButton>
      </div>
    </template>
    <template v-else>
      <p v-if="stage === 'done'" class="set-password-note">现在可以回到群里 @机器人 发「日报」查看昨日战报、发「战绩」查看最近战绩了。</p>
      <p v-else class="load-message" role="alert">{{ error }}</p>
      <div class="set-password-actions">
        <NButton type="primary" @click="emit('closed')">知道了</NButton>
      </div>
    </template>
  </NModal>
</template>
