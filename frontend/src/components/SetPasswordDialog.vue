<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NInput, NModal } from 'naive-ui'
import { api, message, send } from '../api'
import type { User } from '../models'

// QQ 机器人渠道的账号用一次性链接免密登录，进站后在这里补设密码（可顺便改一次账号名）。
const props = defineProps<{ user: User }>()
const emit = defineEmits<{ updated: [value: User] }>()

const PASSWORD_MIN = 10
const USERNAME_RULE = /^[a-z0-9][a-z0-9_.-]{2,63}$/
/** form：填写中；notice：密码已设好但改名失败，只剩提示；closed：本次会话不再弹出。 */
const stage = ref<'form' | 'notice' | 'closed'>('form')
const show = computed(() => stage.value === 'notice' || (stage.value === 'form' && props.user.needs_password === true))
const password = ref('')
const again = ref('')
const newName = ref('')
const busy = ref(false)
const error = ref('')

function close() {
  stage.value = 'closed'
  error.value = ''
}

async function save() {
  error.value = ''
  const name = newName.value.trim().toLowerCase()
  if (password.value.length < PASSWORD_MIN || password.value.length > 256) {
    error.value = `密码长度须为 ${PASSWORD_MIN}–256 个字符`
    return
  }
  if (password.value !== again.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  if (name && (!USERNAME_RULE.test(name) || name.startsWith('qq-'))) {
    error.value = '新账号须为 3–64 位小写字母、数字、点、下划线或连字符，且不能以 qq- 开头'
    return
  }
  if (password.value.toLowerCase() === (name || props.user.username)) {
    error.value = '密码不能与账号相同'
    return
  }
  busy.value = true
  try {
    emit('updated', await api<User>('/account/password', send('PUT', { password: password.value })))
    password.value = ''
    again.value = ''
  } catch (reason) {
    error.value = message(reason)
    busy.value = false
    return
  }
  if (name && name !== props.user.username) {
    try {
      emit('updated', await api<User>('/account/username', send('PATCH', { username: name })))
    } catch (reason) {
      // 密码已经设好，改名失败不影响登录；之后可以在个人主页再改。
      error.value = `密码已设置，但账号名没改成：${message(reason)}。可以稍后在个人主页修改。`
      stage.value = 'notice'
      busy.value = false
      return
    }
  }
  busy.value = false
  close()
}
</script>

<template>
  <NModal :show="show" preset="card" :title="stage === 'notice' ? '密码已设置' : '设置登录密码'"
    class="set-password-modal" :bordered="false" :mask-closable="false" @update:show="value => { if (!value) close() }">
    <form v-if="stage === 'form'" class="login-form" @submit.prevent="save">
      <p class="muted set-password-note">
        你是通过 QQ 机器人的一次性链接登录的。设置密码后，就能直接用账号
        <code>{{ user.username }}</code> 在网页登录。
      </p>
      <label class="filter-field">新密码
        <NInput v-model:value="password" type="password" show-password-on="click" :placeholder="`至少 ${PASSWORD_MIN} 个字符`"
          :input-props="{ autocomplete: 'new-password', maxlength: 256 }" />
      </label>
      <label class="filter-field">确认密码
        <NInput v-model:value="again" type="password" show-password-on="click" placeholder="再输入一次"
          :input-props="{ autocomplete: 'new-password', maxlength: 256 }" />
      </label>
      <label v-if="user.username_editable" class="filter-field">新账号（可选，只能改一次）
        <NInput v-model:value="newName" placeholder="留空则保留当前账号"
          :input-props="{ autocapitalize: 'off', spellcheck: false, maxlength: 64 }" />
      </label>
      <p v-if="error" class="load-message" role="alert">{{ error }}</p>
      <div class="set-password-actions">
        <NButton secondary :disabled="busy" @click="close">稍后再说</NButton>
        <NButton type="primary" attr-type="submit" :loading="busy">保存</NButton>
      </div>
    </form>
    <template v-else>
      <p class="load-message" role="alert">{{ error }}</p>
      <div class="set-password-actions">
        <NButton type="primary" @click="close">知道了</NButton>
      </div>
    </template>
  </NModal>
</template>
