<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { NButton, NIcon, NModal } from 'naive-ui'
import { NotificationsOutline } from '@vicons/ionicons5'
import { api, message, post } from '../api'

interface Notice {
  id: string
  kind: 'announcement' | 'personal'
  title: string
  body: string
  created_at: string
  read: boolean
}

const REFRESH_MS = 5 * 60 * 1000
const items = ref<Notice[]>([])
const unread = ref(0)
const open = ref(false)
const error = ref('')
let timer: number | undefined

const badge = computed(() => (unread.value > 99 ? '99+' : String(unread.value)))
const label = computed(() => (unread.value ? `通知（${unread.value} 条未读）` : '通知'))
const dateFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
})

async function load() {
  try {
    const data = await api<{ unread: number; items: Notice[] }>('/notifications')
    items.value = data.items
    unread.value = data.unread
    error.value = ''
  } catch (reason) {
    error.value = message(reason)
  }
}

async function show() {
  open.value = true
  await load()
  if (!unread.value) return
  try {
    await api('/notifications/read', post({}))
    // 弹窗里仍保留「未读」标记，方便看出哪几条是新的；角标立即清零。
    unread.value = 0
  } catch {
    // 标记失败不影响阅读，下次打开会再试。
  }
}

function close() {
  open.value = false
  items.value = items.value.map(item => ({ ...item, read: true }))
}

function refreshWhenVisible() {
  if (document.visibilityState === 'visible') void load()
}

onMounted(() => {
  void load()
  timer = window.setInterval(refreshWhenVisible, REFRESH_MS)
  document.addEventListener('visibilitychange', refreshWhenVisible)
})
onBeforeUnmount(() => {
  window.clearInterval(timer)
  document.removeEventListener('visibilitychange', refreshWhenVisible)
})
</script>

<template>
  <span class="notice-anchor">
    <NButton quaternary class="theme-toggle" :aria-label="label" :title="label" @click="show">
      <template #icon><NIcon :component="NotificationsOutline" /></template>
    </NButton>
    <!-- 角标放在按钮外、绝对定位，有无未读时铃铛位置都不变 -->
    <span v-if="unread" class="notice-badge" aria-hidden="true">{{ badge }}</span>
  </span>

  <NModal :show="open" preset="card" title="通知" class="notice-modal" :bordered="false"
    @update:show="value => { if (!value) close() }">
    <p v-if="error" class="load-message" role="alert">{{ error }}</p>
    <p v-else-if="!items.length" class="muted notice-empty">暂时没有通知</p>
    <ol v-else class="notice-list">
      <li v-for="item in items" :key="item.id" class="notice-item" :class="{ 'notice-item--unread': !item.read }">
        <header>
          <span class="notice-kind">{{ item.kind === 'announcement' ? '公告' : '个人' }}</span>
          <b>{{ item.title }}</b>
          <time :datetime="item.created_at">{{ dateFormat.format(new Date(item.created_at)) }}</time>
        </header>
        <p>{{ item.body }}</p>
      </li>
    </ol>
  </NModal>
</template>
