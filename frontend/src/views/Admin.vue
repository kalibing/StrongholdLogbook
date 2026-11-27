<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NInput, useDialog } from 'naive-ui'
import { api, message, post, send, useResource } from '../api'
import { logbook } from '../context'
import type { AdminNotice } from '../models'

// 公告管理：只有管理员账号能打开（后端按管理员名单校验，这里只负责展示）。
const TITLE_LIMIT = 60
const BODY_LIMIT = 2000
const { user } = logbook()
const allowed = computed(() => user.value?.is_admin === true)
const revision = ref(0)
const { data, error, pending } = useResource<{ items: AdminNotice[] }>(
  computed(() => (allowed.value ? '/admin/notifications' : null)), revision, true)
const items = computed(() => data.value?.items ?? [])

const audience = ref<'all' | 'user'>('all')
const username = ref('')
const title = ref('')
const body = ref('')
const publishing = ref(false)
const formError = ref('')
const formNotice = ref('')
const dialog = useDialog()

const dateFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
})

async function publish() {
  formError.value = ''
  formNotice.value = ''
  if (!title.value.trim() || !body.value.trim()) {
    formError.value = '标题和正文都不能为空'
    return
  }
  if (audience.value === 'user' && !username.value.trim()) {
    formError.value = '请填写收件账号'
    return
  }
  publishing.value = true
  try {
    await api('/admin/notifications', post({
      title: title.value,
      body: body.value,
      username: audience.value === 'user' ? username.value.trim() : null,
    }))
    formNotice.value = audience.value === 'all' ? '公告已发布，所有账号都能在铃铛里看到。' : `已发送给 ${username.value.trim()}。`
    title.value = ''
    body.value = ''
    revision.value++
  } catch (reason) {
    formError.value = message(reason)
  } finally {
    publishing.value = false
  }
}

function confirmRemove(item: AdminNotice) {
  dialog.warning({
    title: '删除这条通知？',
    content: `「${item.title}」会从所有收件人的通知列表里消失，无法恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api(`/admin/notifications/${item.id}`, send('DELETE'))
        revision.value++
      } catch (reason) {
        formError.value = message(reason)
      }
    },
  })
}
</script>

<template>
  <section v-if="!allowed" class="panel admin-panel">
    <p class="muted" role="status">这个页面只对管理员开放。需要发布公告请联系站长授予权限。</p>
  </section>
  <div v-else class="admin-layout">
    <section class="panel admin-panel" aria-labelledby="publish-title">
      <div class="section-heading"><h2 id="publish-title">发布通知</h2></div>
      <form class="admin-form" @submit.prevent="publish">
        <fieldset class="admin-audience" aria-label="发送范围" :disabled="publishing">
          <label><input v-model="audience" type="radio" name="audience" value="all">全站公告</label>
          <label><input v-model="audience" type="radio" name="audience" value="user">发给单个账号</label>
        </fieldset>
        <NInput v-if="audience === 'user'" v-model:value="username" :maxlength="64" placeholder="收件人的登录账号"
          aria-label="收件账号" :input-props="{ autocapitalize: 'off', spellcheck: false }" />
        <NInput v-model:value="title" :maxlength="TITLE_LIMIT" show-count placeholder="标题" aria-label="标题" />
        <NInput v-model:value="body" type="textarea" :maxlength="BODY_LIMIT" show-count :autosize="{ minRows: 4, maxRows: 12 }"
          placeholder="正文，按纯文本显示，可以换行" aria-label="正文" />
        <div class="admin-actions">
          <NButton type="primary" attr-type="submit" :loading="publishing">{{ audience === 'all' ? '发布公告' : '发送通知' }}</NButton>
          <span v-if="formNotice" class="muted" role="status">{{ formNotice }}</span>
        </div>
        <p v-if="formError" class="load-message" role="alert">{{ formError }}</p>
      </form>
    </section>

    <section class="panel admin-panel" aria-labelledby="history-title">
      <div class="section-heading"><h2 id="history-title">最近通知</h2></div>
      <p v-if="error" class="load-message" role="alert">{{ error }}</p>
      <p v-else-if="pending && !data" class="muted" role="status">正在加载…</p>
      <p v-else-if="!items.length" class="muted notice-empty">还没有发过通知</p>
      <ol v-else class="notice-list">
        <li v-for="item in items" :key="item.id" class="notice-item">
          <header>
            <span class="notice-kind">{{ item.kind === 'announcement' ? '公告' : `给 ${item.username}` }}</span>
            <b>{{ item.title }}</b>
            <time :datetime="item.created_at">{{ dateFormat.format(new Date(item.created_at)) }}</time>
            <NButton size="small" quaternary type="error" @click="confirmRemove(item)">删除</NButton>
          </header>
          <p>{{ item.body }}</p>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.admin-layout { display: grid; gap: 1.25rem; }
.admin-panel { padding: 1.25rem 1.5rem; }
.admin-form { display: grid; gap: .85rem; max-width: 40rem; }
.admin-audience { display: flex; flex-wrap: wrap; gap: 1.25rem; margin: 0; padding: 0; border: 0; }
.admin-audience label { display: inline-flex; align-items: center; gap: .4rem; cursor: pointer; }
.admin-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .85rem; }
.admin-form .load-message { margin: 0; }
@media (max-width: 640px) {
  .admin-panel { padding: 1rem; }
}
</style>
