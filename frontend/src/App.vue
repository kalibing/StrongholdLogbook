<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NConfigProvider, NDialogProvider, NIcon, NInput, NMessageProvider, darkTheme, dateZhCN, zhCN } from 'naive-ui'
import { MoonOutline, PersonCircleOutline, SunnyOutline } from '@vicons/ionicons5'
import type { GlobalThemeOverrides } from 'naive-ui'
import { api, ApiError, message, post } from './api'
import { logbookKey, newFilters, type Theme } from './context'
import type { Facet, User } from './models'
import HeadingArt from './components/HeadingArt.vue'

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
    primaryColorHover: theme.value === 'dark' ? '#eaf0be' : '#5f701b',
    primaryColorPressed: theme.value === 'dark' ? '#c9d296' : '#516017',
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
  if (!nav.value) return
  const active = nav.value.querySelector<HTMLElement>('a[aria-current="page"]')
  // 「个人主页」不在主导航里：收起指示条，而不是停在上一页的位置。
  if (!active) {
    indicator.value = { ...indicator.value, width: 0 }
    return
  }
  const rect = active.getBoundingClientRect()
  const base = nav.value.getBoundingClientRect()
  indicator.value = { left: rect.left - base.left + 8, width: Math.max(12, rect.width - 16) }
}
const titles = [
  { route: 'overview', title: '战绩总览' },
  { route: 'yesterday', title: '昨日战报' },
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

type TransitionDocument = Document & { startViewTransition?: (update: () => Promise<void>) => { ready: Promise<void> } }

/**
 * 切换光暗：支持 View Transitions 的浏览器里，新主题从切换按钮处以圆形扩散铺开；
 * 不支持或开启「减少动态效果」时直接切换。
 */
async function toggleTheme(event?: Event) {
  const next: Theme = theme.value === 'dark' ? 'light' : 'dark'
  const doc = document as TransitionDocument
  if (!doc.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    applyTheme(next)
    return
  }
  // 用按钮中心而不是鼠标坐标：键盘触发时 clientX/Y 是 0。
  const target = event?.currentTarget instanceof Element ? event.currentTarget.getBoundingClientRect() : null
  const x = target ? target.left + target.width / 2 : window.innerWidth - 48
  const y = target ? target.top + target.height / 2 : 32
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
  const transition = doc.startViewTransition(async () => {
    applyTheme(next)
    await nextTick()
  })
  try {
    await transition.ready
  } catch {
    return
  }
  document.documentElement.animate(
    { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
    { duration: 560, easing: 'cubic-bezier(.65, 0, .25, 1)', pseudoElement: '::view-transition-new(root)' },
  )
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

// 退出失败只提示一行，不能借用 error：它会把整页内容换成「重试会话」。
const logoutError = ref('')
async function logout() {
  logoutError.value = ''
  try {
    await api('/session', { method: 'DELETE' })
    resetSession()
  } catch (reason) {
    logoutError.value = `退出登录失败：${message(reason)}`
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

function setUser(value: User) {
  user.value = value
}
const accountName = computed(() => user.value?.display_name || user.value?.username || '')

provide(logbookKey, { filters, user, setUser, facets, revision, theme, toggleTheme, refresh })
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
            <NIcon :key="theme" class="theme-toggle-icon" :component="theme === 'dark' ? SunnyOutline : MoonOutline" />
          </template>
        </NButton>
        <RouterLink v-if="user" class="account-chip" :to="{ name: 'profile' }" title="个人主页"
          :aria-current="route.name === 'profile' ? 'page' : undefined">
          <img v-if="user.avatar_url" class="account-chip-avatar" :src="user.avatar_url" alt="">
          <NIcon v-else :component="PersonCircleOutline" :size="18" aria-hidden="true" />
          <span>{{ accountName }}</span>
        </RouterLink>
        <NButton v-if="user" size="small" secondary @click="logout">退出登录</NButton>
      </div>
    </div>
  </header>

  <main class="layout">
    <div v-if="pending" class="loading-shell" role="status">正在读取数据…</div>

    <template v-else-if="user || route.meta.public">
      <div class="heading">
        <div class="heading-copy">
          <p class="eyebrow">卫戍协议 <span>/</span> {{ accountName || '本地资源' }}</p>
          <h1>{{ route.meta.title }}</h1>
          <p class="heading-description">{{ route.meta.description }}</p>
        </div>
        <HeadingArt />
      </div>
      <p v-if="logoutError" class="load-message" role="alert">{{ logoutError }} <button type="button" @click="logout">重试</button></p>
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
