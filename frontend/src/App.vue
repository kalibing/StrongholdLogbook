<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NConfigProvider, NDialogProvider, NDropdown, NIcon, NInput, NMessageProvider, darkTheme, dateZhCN, zhCN } from 'naive-ui'
import {
  CalendarOutline, CloseOutline, CloudDownloadOutline, GridOutline, ListOutline, LogOutOutline, MenuOutline,
  MegaphoneOutline, MoonOutline, PeopleOutline, PersonOutline, RibbonOutline, SunnyOutline,
} from '@vicons/ionicons5'
import type { DropdownOption, GlobalThemeOverrides } from 'naive-ui'
import { api, ApiError, message, post } from './api'
import { logbookKey, newFilters, type Theme } from './context'
import type { Facet, User } from './models'
import HeadingArt from './components/HeadingArt.vue'
import LogoMark from './components/LogoMark.vue'
import NotificationBell from './components/NotificationBell.vue'
import SetPasswordDialog from './components/SetPasswordDialog.vue'

const STORAGE_THEME = 'logbook:theme'
const USERNAME_RULE = /^[a-z0-9][a-z0-9_.-]{2,63}$/
const USERNAME_HINT = '账号须为 3–64 位小写字母、数字、点、下划线或连字符，且以字母或数字开头'
const route = useRoute()
const router = useRouter()
const user = ref<User | null>(null)
const facets = ref<Facet[]>([])
const filters = reactive(newFilters())
const revision = ref(0)
const pending = ref(true)
const error = ref('')
const username = ref('')
const password = ref('')
const loggingIn = ref(false)
/** 登录页的两种表单；注册入口只在服务端开放注册时出现。 */
const authMode = ref<'login' | 'register'>('login')
const registration = ref<{ enabled: boolean }>({ enabled: false })
const newUsername = ref('')
const newPassword = ref('')
const newPasswordAgain = ref('')
const PASSWORD_MIN = 10
const registering = ref(false)
const theme = ref<Theme>('dark')
/** 窄屏时侧边栏收成抽屉，这里记录是否展开。 */
const navOpen = ref(false)
const overrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: theme.value === 'dark' ? '#e1ea8f' : '#62731a',
    primaryColorHover: theme.value === 'dark' ? '#ecf2b4' : '#566516',
    primaryColorPressed: theme.value === 'dark' ? '#c8d27a' : '#4a5812',
    borderRadius: '2px',
    borderRadiusSmall: '2px',
    fontFamily: 'inherit',
    // 组件库默认 14px；中文界面主体文字用 16px，表单 / 表格 / 下拉随之放大
    fontSize: '16px',
    fontSizeTiny: '14px',
    fontSizeSmall: '15px',
    fontSizeMedium: '16px',
    fontSizeLarge: '17px',
    fontSizeHuge: '18px',
    fontWeightStrong: '600',
    bodyColor: 'transparent',
    cardColor: theme.value === 'dark' ? '#0f1314' : '#ffffff',
    modalColor: theme.value === 'dark' ? '#0f1314' : '#ffffff',
    popoverColor: theme.value === 'dark' ? '#131819' : '#ffffff',
    borderColor: theme.value === 'dark' ? '#253033' : '#d3dbd8',
    textColorBase: theme.value === 'dark' ? '#eef2f0' : '#172022',
    textColor2: theme.value === 'dark' ? '#c6cfcc' : '#36423f',
    placeholderColor: theme.value === 'dark' ? '#97a39f' : '#5a6865',
  },
}))

const navItems = [
  { route: 'overview', title: '战绩总览', icon: GridOutline },
  { route: 'yesterday', title: '昨日战报', icon: CalendarOutline },
  { route: 'matches', title: '对局记录', icon: ListOutline },
  { route: 'operators', title: '干员统计', icon: PeopleOutline },
  { route: 'achievements', title: '成就档案', icon: RibbonOutline },
  { route: 'data-import', title: '数据导入', icon: CloudDownloadOutline },
]
/** 管理员额外看到管理后台，权限由后端校验。 */
const visibleNav = computed(() => user.value?.is_admin
  ? [...navItems, { route: 'admin', title: '管理后台', icon: MegaphoneOutline }]
  : navItems)


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

const QQ_LINK_PREFIX = '#qq-login='

/** 从地址栏取出 QQ 一次性登录令牌，并立刻抹掉，避免留在历史记录或被分享出去。 */
function takeQqLinkToken(): string | null {
  if (!window.location.hash.startsWith(QQ_LINK_PREFIX)) return null
  const token = decodeURIComponent(window.location.hash.slice(QQ_LINK_PREFIX.length))
  window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search)
  return token || null
}

/** 已打开页面时再点同一站点的登录链接，只会改 # 片段、不会刷新页面。 */
function onHashChange() {
  if (window.location.hash.startsWith(QQ_LINK_PREFIX)) void restoreSession()
}

async function restoreSession() {
  pending.value = true
  error.value = ''
  const linkToken = takeQqLinkToken()
  if (linkToken) {
    try {
      user.value = await api<User>('/session/qq-link', post({ token: linkToken }))
      pending.value = false
      return
    } catch (reason) {
      // 链接失效时退回普通流程：已登录就继续用原会话，否则在登录页显示原因。
      const linkError = message(reason)
      try {
        user.value = await api<User>('/session')
      } catch {
        error.value = linkError
      }
      pending.value = false
      return
    }
  }
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

async function loadRegistration() {
  try {
    registration.value = await api<{ enabled: boolean }>('/registration')
  } catch {
    registration.value = { enabled: false }
  }
}

function switchAuth(mode: 'login' | 'register') {
  authMode.value = mode
  error.value = ''
}

async function register() {
  error.value = ''
  const value = newUsername.value.trim().toLowerCase()
  if (!USERNAME_RULE.test(value)) {
    error.value = USERNAME_HINT
    return
  }
  if (value.startsWith('qq-')) {
    error.value = '以 qq- 开头的账号保留给 QQ 机器人注册'
    return
  }
  if (newPassword.value.length < PASSWORD_MIN || newPassword.value.length > 256) {
    error.value = `密码长度须为 ${PASSWORD_MIN}–256 个字符`
    return
  }
  if (newPassword.value !== newPasswordAgain.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  if (newPassword.value.toLowerCase() === value) {
    error.value = '密码不能与账号相同'
    return
  }
  registering.value = true
  try {
    user.value = await api<User>('/register', post({ username: value, password: newPassword.value }))
    newUsername.value = ''
    newPassword.value = ''
    newPasswordAgain.value = ''
    authMode.value = 'login'
  } catch (reason) {
    error.value = message(reason)
  } finally {
    registering.value = false
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

watch(() => route.fullPath, () => { navOpen.value = false })
function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') navOpen.value = false
}
onMounted(() => {
  const stored = (document.documentElement.dataset.theme as Theme | undefined)
    ?? (window.localStorage.getItem(STORAGE_THEME) as Theme | null)
  applyTheme(stored === 'light' ? 'light' : 'dark')
  window.addEventListener('logbook-logout', resetSession)
  window.addEventListener('keydown', onKey)
  window.addEventListener('hashchange', onHashChange)
  void restoreSession()
  void loadRegistration()
})
onBeforeUnmount(() => {
  window.removeEventListener('logbook-logout', resetSession)
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('hashchange', onHashChange)
})

function setUser(value: User) {
  user.value = value
}
const accountName = computed(() => user.value?.display_name || user.value?.username || '')
const accountInitial = computed(() => Array.from(accountName.value)[0]?.toUpperCase() ?? '?')

/** 侧栏底部账号卡的下拉菜单：顶部显示昵称与登录账号，下面是个人主页和退出登录。 */
const menuIcon = (icon: typeof PersonOutline) => () => h(NIcon, { component: icon })
const accountMenu = computed<DropdownOption[]>(() => [
  {
    key: 'who', type: 'render',
    render: () => h('div', { class: 'account-menu-head' }, [
      h('strong', accountName.value),
      h('small', `账号 ${user.value?.username ?? ''}`),
    ]),
  },
  { key: 'divider', type: 'divider' },
  { key: 'profile', label: '个人主页', icon: menuIcon(PersonOutline) },
  { key: 'logout', label: '退出登录', icon: menuIcon(LogOutOutline) },
])
function selectAccount(key: string) {
  if (key === 'profile') void router.push({ name: 'profile' })
  if (key === 'logout') void logout()
}

provide(logbookKey, { filters, user, setUser, facets, revision, theme, toggleTheme, refresh })
</script>

<template>
  <NConfigProvider :theme="theme === 'dark' ? darkTheme : null" :theme-overrides="overrides" :locale="zhCN" :date-locale="dateZhCN">
  <NMessageProvider>
  <NDialogProvider>
  <div class="shell" :class="{ 'shell--bare': !user, 'shell--nav-open': navOpen }">
    <aside v-if="user" id="sidebar" class="sidebar" aria-label="侧边栏">
      <RouterLink class="side-brand" to="/">
        <LogoMark :size="32" />
        <span class="side-brand-copy"><b>卫戍协议</b><small>作战档案</small></span>
      </RouterLink>

      <nav class="side-nav" aria-label="主导航">
        <RouterLink v-for="item in visibleNav" :key="item.route" class="side-link" :to="{ name: item.route }"
          :title="item.title" :aria-current="route.name === item.route ? 'page' : undefined">
          <NIcon class="side-icon" :component="item.icon" aria-hidden="true" />
          <span class="side-text">{{ item.title }}</span>
        </RouterLink>
      </nav>

      <div class="side-foot">
        <div class="side-account">
          <NDropdown trigger="click" placement="top-start" :options="accountMenu" @select="selectAccount">
            <button type="button" class="account-card" :class="{ 'account-card--active': route.name === 'profile' }"
              :aria-label="`账号菜单：${accountName}`" :title="accountName">
              <span class="account-avatar" aria-hidden="true">
                <img v-if="user.avatar_url" :src="user.avatar_url" alt="">
                <span v-else>{{ accountInitial }}</span>
              </span>
              <span class="account-copy"><b>{{ accountName }}</b><small>@{{ user.username }}</small></span>
            </button>
          </NDropdown>
          <NotificationBell :key="user.username" />
          <SetPasswordDialog :user="user" @updated="setUser" />
          <NButton quaternary class="theme-toggle" :aria-label="theme === 'dark' ? '切换到浅色' : '切换到深色'"
            :title="theme === 'dark' ? '切换到浅色' : '切换到深色'" @click="toggleTheme">
            <template #icon>
              <NIcon :key="theme" class="theme-toggle-icon" :component="theme === 'dark' ? SunnyOutline : MoonOutline" />
            </template>
          </NButton>
        </div>
      </div>
    </aside>
    <button v-if="user" type="button" class="side-scrim" tabindex="-1" aria-hidden="true" @click="navOpen = false"></button>

    <div class="workspace">
      <header class="topbar">
        <NButton v-if="user" quaternary class="topbar-menu" :aria-label="navOpen ? '收起导航' : '展开导航'"
          aria-controls="sidebar" :aria-expanded="navOpen" @click="navOpen = !navOpen">
          <template #icon><NIcon :component="navOpen ? CloseOutline : MenuOutline" /></template>
        </NButton>
        <RouterLink class="side-brand side-brand--compact" to="/">
          <LogoMark :size="26" />
          <span class="side-brand-copy"><b>卫戍协议</b><small>作战档案</small></span>
        </RouterLink>
        <NButton quaternary class="theme-toggle" :aria-label="theme === 'dark' ? '切换到浅色' : '切换到深色'"
          :title="theme === 'dark' ? '切换到浅色' : '切换到深色'" @click="toggleTheme">
          <template #icon>
            <NIcon :key="theme" class="theme-toggle-icon" :component="theme === 'dark' ? SunnyOutline : MoonOutline" />
          </template>
        </NButton>
      </header>

      <main class="layout">
        <div v-if="pending" class="loading-shell" role="status"><i aria-hidden="true"></i>正在读取数据…</div>

        <template v-else-if="user || route.meta.public">
          <div class="heading">
            <div class="heading-copy">
              <h1>{{ route.meta.title }}</h1>
              <p class="heading-description">{{ route.meta.description }}</p>
            </div>
            <HeadingArt />
            <i class="heading-scan" aria-hidden="true"></i>
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
              <h1 id="login-title">{{ authMode === 'login' ? '登录' : '注册' }}</h1>
              <p class="muted">
                {{ authMode === 'login'
                  ? '登录后查看对局记录、盟约趋势和干员出场统计。'
                  : '自己设置登录账号和密码，注册后直接登录。' }}
              </p>
            </header>
            <form v-if="authMode === 'register'" class="login-form" @submit.prevent="register">
              <label class="filter-field">账号
                <NInput v-model:value="newUsername" size="large" placeholder="小写字母、数字、. _ -，3–64 位"
                  :input-props="{ autocomplete: 'username', autocapitalize: 'off', spellcheck: false, maxlength: 64 }" />
              </label>
              <label class="filter-field">密码
                <NInput v-model:value="newPassword" type="password" size="large" show-password-on="click"
                  :placeholder="`至少 ${PASSWORD_MIN} 个字符`" :input-props="{ autocomplete: 'new-password', maxlength: 256 }" />
              </label>
              <label class="filter-field">确认密码
                <NInput v-model:value="newPasswordAgain" type="password" size="large" show-password-on="click"
                  placeholder="再输入一次" :input-props="{ autocomplete: 'new-password', maxlength: 256 }" />
              </label>
              <p v-if="error" class="load-message" role="alert">{{ error }}</p>
              <NButton type="primary" size="large" block attr-type="submit" :loading="registering">
                {{ registering ? '创建中…' : '创建账号' }}
              </NButton>
              <p class="auth-switch">已有账号？<button type="button" @click="switchAuth('login')">返回登录</button></p>
            </form>
            <form v-else class="login-form" @submit.prevent="login">
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
              <p v-if="registration.enabled" class="auth-switch">
                还没有账号？<button type="button" @click="switchAuth('register')">注册账号</button>
              </p>
            </form>
          </section>
        </div>
      </main>
    </div>
  </div>
  </NDialogProvider>
  </NMessageProvider>
  </NConfigProvider>
</template>
