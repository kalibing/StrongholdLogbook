<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NConfigProvider, NDialogProvider, NIcon, NInput, NMessageProvider, darkTheme, dateZhCN, zhCN } from 'naive-ui'
import { MoonOutline, SunnyOutline } from '@vicons/ionicons5'
import type { GlobalThemeOverrides } from 'naive-ui'
import { api, ApiError, message, post } from './api'
import { logbookKey, newFilters, type Theme } from './context'
import type { Facet, User } from './models'

const STORAGE_THEME = 'logbook:theme'
const route = useRoute()
const user = ref<User | null>(null)
const facets = ref<Facet[]>([])
const filters = reactive(newFilters())
const revision = ref(0)
const pending = ref(true)
const error = ref('')
const username = ref('')
const password = ref('')
const loggingIn = ref(false)
const theme = ref<Theme>('dark')
const nav = ref<HTMLElement | null>(null)
const indicator = ref({ left: 0, width: 0 })
const overrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: theme.value === 'dark' ? '#dfe6a8' : '#687820',
    primaryColorHover: theme.value === 'dark' ? '#eaf0be' : '#7f9130',
    primaryColorPressed: theme.value === 'dark' ? '#c9d296' : '#5f6c1e',
    borderRadius: '3px',
    borderRadiusSmall: '2px',
    fontFamily: 'inherit',
    bodyColor: 'transparent',
    cardColor: theme.value === 'dark' ? '#12141a' : '#ffffff',
    modalColor: theme.value === 'dark' ? '#12141a' : '#ffffff',
    popoverColor: theme.value === 'dark' ? '#161a22' : '#ffffff',
    borderColor: theme.value === 'dark' ? '#2a313c' : '#d8dfe7',
    textColorBase: theme.value === 'dark' ? '#f3f4f6' : '#1a212b',
    textColor2: theme.value === 'dark' ? '#c9d0da' : '#3b4653',
    placeholderColor: theme.value === 'dark' ? '#a4acb8' : '#5d6a78',
  },
}))

function measureNav() {
  const active = nav.value?.querySelector<HTMLElement>('a[aria-current="page"]')
  if (!active || !nav.value) return
  const rect = active.getBoundingClientRect()
  const base = nav.value.getBoundingClientRect()
  indicator.value = { left: rect.left - base.left + 8, width: Math.max(12, rect.width - 16) }
}
const titles = [
  { route: 'overview', title: '战绩总览' },
  { route: 'matches', title: '对局记录' },
  { route: 'operators', title: '干员统计' },
  { route: 'achievements', title: '成就档案' },
  { route: 'data-import', title: '数据导入' },
]

function applyTheme(value: Theme) {
  theme.value = value
  document.documentElement.dataset.theme = value
  try {
    window.localStorage.setItem(STORAGE_THEME, value)
  } catch {
    // 隐私模式下无法写入，忽略即可。
  }
}

function toggleTheme() {
  applyTheme(theme.value === 'dark' ? 'light' : 'dark')
}

function resetSession() {
  user.value = null
  facets.value = []
}

async function restoreSession() {
  pending.value = true
  error.value = ''
  try {
    user.value = await api<User>('/session')
  } catch (reason) {
    if (!(reason instanceof ApiError && reason.status === 401)) error.value = message(reason)
  } finally {
    pending.value = false
  }
}

async function login() {
  error.value = ''
  loggingIn.value = true
  try {
    user.value = await api<User>('/session', post({ username: username.value.trim().toLowerCase(), password: password.value }))
    password.value = ''
  } catch (reason) {
    error.value = message(reason)
  } finally {
    loggingIn.value = false
  }
}

async function logout() {
  try {
    await api('/session', { method: 'DELETE' })
    resetSession()
  } catch (reason) {
    error.value = message(reason)
  }
}

function refresh() {
  revision.value++
}

async function loadFacets() {
  if (!user.value) return
  try {
    facets.value = await api<Facet[]>('/facets')
  } catch {
    // 具体页面会展示连接与权限错误。
  }
}

watch([revision, user], () => { void loadFacets() })

watch([() => route.name, user], () => { void nextTick(measureNav) })
onMounted(() => {
  const stored = (document.documentElement.dataset.theme as Theme | undefined)
    ?? (window.localStorage.getItem(STORAGE_THEME) as Theme | null)
  applyTheme(stored === 'light' ? 'light' : 'dark')
  window.addEventListener('logbook-logout', resetSession)
  window.addEventListener('resize', measureNav)
  void restoreSession()
  void nextTick(measureNav)
})
onBeforeUnmount(() => {
  window.removeEventListener('logbook-logout', resetSession)
  window.removeEventListener('resize', measureNav)
})

provide(logbookKey, { filters, facets, revision, theme, toggleTheme, refresh })
</script>

<template>
  <NConfigProvider :theme="theme === 'dark' ? darkTheme : null" :theme-overrides="overrides" :locale="zhCN" :date-locale="dateZhCN">
  <NMessageProvider>
  <NDialogProvider>
  <header class="site-header">
    <div class="header-inner">
      <RouterLink class="brand" to="/"><i class="shield" aria-hidden="true"></i>卫戍协议<span>作战档案</span></RouterLink>
      <nav v-if="user" ref="nav" aria-label="主导航">
        <i class="nav-indicator" :style="{ transform: `translateX(${indicator.left}px)`, width: indicator.width + 'px' }" aria-hidden="true"></i>
        <RouterLink v-for="item in titles" :key="item.route" :to="{ name: item.route }"
          :aria-current="route.name === item.route ? 'page' : undefined">{{ item.title }}</RouterLink>
      </nav>
      <div class="account-actions">
        <NButton quaternary circle size="small" class="theme-toggle"
          :aria-label="theme === 'dark' ? '切换到浅色' : '切换到深色'"
          :title="theme === 'dark' ? '切换到浅色' : '切换到深色'" @click="toggleTheme">
          <template #icon>
            <NIcon :component="theme === 'dark' ? SunnyOutline : MoonOutline" />
          </template>
        </NButton>
        <NButton v-if="user" size="small" secondary @click="logout">退出登录</NButton>
      </div>
    </div>
  </header>

  <main class="layout">
    <div v-if="pending" class="loading-shell" role="status">正在读取数据…</div>

    <template v-else-if="user || route.meta.public">
      <div class="heading" :class="{ 'heading-compact': route.name !== 'overview' }">
        <div class="heading-copy">
          <p class="eyebrow">卫戍协议 <span>/</span> {{ user?.username ?? '本地资源' }}</p>
          <h1>{{ route.meta.title }}</h1>
          <p class="heading-description">{{ route.meta.description }}</p>
        </div>
        <div class="heading-art" aria-hidden="true"><i></i></div>
      </div>
      <p v-if="error" class="load-message" role="alert">{{ error }} <button type="button" @click="restoreSession">重试</button></p>
      <RouterView v-else v-slot="{ Component, route: pageRoute }">
        <Transition name="page">
          <div :key="pageRoute.name" class="route-content"><component :is="Component" /></div>
        </Transition>
      </RouterView>
    </template>

    <div v-else class="login-layout">
      <section class="panel login-panel" aria-labelledby="login-title">
        <header class="login-head">
          <p class="eyebrow">卫戍协议 <span>/</span> 作战档案</p>
          <h1 id="login-title">登录</h1>
          <p class="muted">对局记录、盟约趋势和干员出场统计。</p>
        </header>
        <form class="login-form" @submit.prevent="login">
          <label class="filter-field">用户名
            <NInput v-model:value="username" size="large" placeholder="用户名" :input-props="{ autocomplete: 'username', maxlength: 64 }" />
          </label>
          <label class="filter-field">密码
            <NInput v-model:value="password" type="password" size="large" show-password-on="click"
              placeholder="密码" :input-props="{ autocomplete: 'current-password', maxlength: 256 }" />
          </label>
          <p v-if="error" class="load-message" role="alert">{{ error }}</p>
          <NButton type="primary" size="large" block attr-type="submit" :loading="loggingIn">
            {{ loggingIn ? '登录中…' : '登录' }}
          </NButton>
        </form>
      </section>
    </div>
  </main>
  </NDialogProvider>
  </NMessageProvider>
  </NConfigProvider>
</template>
