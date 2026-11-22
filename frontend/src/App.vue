<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, ApiError, message, post } from './api'
import { logbookKey, newFilters } from './context'
import type { Facet, Role, User } from './models'

const STORAGE_ROLE = 'logbook:role'
const route = useRoute()
const user = ref<User | null>(null)
const roles = ref<Role[]>([])
const activeRole = ref('')
const role = computed(() => roles.value.find(item => item.id === activeRole.value) ?? null)
const facets = ref<Facet[]>([])
const filters = reactive(newFilters())
const revision = ref(0)
const pending = ref(true)
const error = ref('')
const username = ref('')
const password = ref('')
const loggingIn = ref(false)
const titles = [
  { route: 'overview', title: '战绩总览' },
  { route: 'matches', title: '对局记录' },
  { route: 'operators', title: '干员统计' },
  { route: 'archive', title: '档案管理' },
]

const eyebrow = computed(() => role.value?.name ?? '规程协议 1')

function storedRole(): string {
  try {
    return window.localStorage.getItem(STORAGE_ROLE) ?? ''
  } catch {
    return ''
  }
}

function rememberRole(id: string) {
  try {
    if (id) window.localStorage.setItem(STORAGE_ROLE, id)
    else window.localStorage.removeItem(STORAGE_ROLE)
  } catch {
    // 隐私模式下无法写入，忽略即可。
  }
}

function resetSession() {
  user.value = null
  roles.value = []
  activeRole.value = ''
  facets.value = []
}

function selectRole(id: string) {
  if (roles.value.some(item => item.id === id)) activeRole.value = id
}

async function fetchRoles() {
  roles.value = await api<Role[]>('/roles')
  if (!role.value) {
    const remembered = roles.value.find(item => item.id === storedRole())
    activeRole.value = (remembered ?? roles.value[0])?.id ?? ''
  }
}

async function restoreSession() {
  pending.value = true
  error.value = ''
  try {
    user.value = await api<User>('/session')
    await fetchRoles()
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
    await fetchRoles()
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

async function createRole(name: string) {
  const created = await api<Role>('/roles', post({ name }))
  roles.value = [...roles.value, created]
  activeRole.value = created.id
}

async function renameRole(id: string, name: string) {
  const updated = await api<Role>('/roles/' + id, { ...post({ name }), method: 'PATCH' })
  roles.value = roles.value.map(item => (item.id === id ? updated : item))
}

async function deleteRole(id: string) {
  await api('/roles/' + id, { method: 'DELETE' })
  roles.value = roles.value.filter(item => item.id !== id)
  if (activeRole.value === id) activeRole.value = roles.value[0]?.id ?? ''
  revision.value++
}

function refresh() {
  revision.value++
}

watch(activeRole, id => {
  Object.assign(filters, newFilters())
  rememberRole(id)
})
watch([activeRole, revision], async ([id], _, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  facets.value = []
  if (!id) return
  try {
    const values = await api<Facet[]>('/roles/' + id + '/facets', { signal: controller.signal })
    if (!controller.signal.aborted) facets.value = values
  } catch {
    // 具体页面会展示连接与权限错误。
  }
})

onMounted(() => {
  window.addEventListener('logbook-logout', resetSession)
  void restoreSession()
})
onBeforeUnmount(() => window.removeEventListener('logbook-logout', resetSession))

provide(logbookKey, {
  role, roles, facets, filters, revision,
  createRole, renameRole, deleteRole, selectRole, refresh,
})
</script>

<template>
  <header class="site-header">
    <div class="header-inner">
      <RouterLink class="brand" to="/"><i class="shield" aria-hidden="true"></i>卫戍协议<span>作战档案</span></RouterLink>
      <nav v-if="user" aria-label="主导航">
        <RouterLink v-for="item in titles" :key="item.route" :to="{ name: item.route }"
          :aria-current="route.name === item.route ? 'page' : undefined">{{ item.title }}</RouterLink>
      </nav>
      <div v-if="user" class="account-actions">
        <span v-if="roles.length" class="select-field">
          <select v-model="activeRole" aria-label="当前角色档案">
            <option v-for="item in roles" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
        </span>
        <button type="button" id="account" @click="logout">退出登录</button>
      </div>
    </div>
  </header>

  <main class="layout">
    <p v-if="pending" class="load-message panel" role="status">正在读取数据…</p>

    <template v-else-if="user">
      <div class="heading" :class="{ 'heading-compact': route.name !== 'overview' }">
        <div class="heading-copy">
          <p class="eyebrow">卫戍协议 <span>/</span> {{ eyebrow }}</p>
          <h1>{{ route.meta.title }}</h1>
          <p class="heading-description">{{ route.meta.description }}</p>
        </div>
        <div class="heading-art" aria-hidden="true"><i></i></div>
      </div>
      <p v-if="error" class="load-message" role="alert">{{ error }} <button type="button" @click="restoreSession">重试</button></p>
      <section v-else-if="!role && route.name !== 'archive'" class="panel empty-state">
        <span>建立角色档案后即可导入和查看战绩。</span>
        <RouterLink class="button-link" to="/archive">创建角色档案</RouterLink>
      </section>
      <RouterView v-else />
    </template>

    <div v-else class="login-layout">
      <div class="heading">
        <div class="heading-copy">
          <p class="eyebrow">卫戍协议 <span>/</span> 作战档案</p>
          <h1>作战档案</h1>
          <p class="heading-description">对局记录、盟约趋势和干员出场统计。</p>
        </div>
        <div class="heading-art" aria-hidden="true"><i></i></div>
      </div>
      <section class="panel login-panel" aria-labelledby="login-title">
        <h2 id="login-title">登录</h2>
        <form @submit.prevent="login">
          <label class="filter-field">用户名
            <input v-model="username" autocomplete="username" required maxlength="64">
          </label>
          <label class="filter-field">密码
            <input v-model="password" autocomplete="current-password" type="password" required maxlength="256">
          </label>
          <p v-if="error" class="load-message" role="alert">{{ error }}</p>
          <button type="submit" class="login-submit" :disabled="loggingIn">{{ loggingIn ? '登录中…' : '登录' }}</button>
        </form>
      </section>
    </div>
  </main>
</template>
