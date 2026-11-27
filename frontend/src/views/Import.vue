<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { NButton, NIcon, NInput, NModal } from 'naive-ui'
import { ChevronForwardOutline } from '@vicons/ionicons5'
import { api, ApiError, message, post } from '../api'
import { logbook } from '../context'
import { dateTime } from '../format'
import type { ImportJob } from '../models'
import StepWizard from '../components/StepWizard.vue'

interface ImportReceipt {
  id: string
  total: number
  records?: number
  token_saved?: boolean
}

interface Credentials {
  cred: string
  sign: string
}

const { refresh } = logbook()
const jobs = ref<ImportJob[]>([])
const jobsError = ref('')
const jobsPending = ref(false)
const totalMatches = ref<number | null>(null)
const showForm = ref(true)
const hasSavedToken = ref(false)
const loadingSavedToken = ref(true)
const replacingToken = ref(false)
const clearingToken = ref(false)
const tokenStatusError = ref('')
const pulling = ref(false)
const pullError = ref('')
const pasting = ref(false)
const pasteHint = ref('')
const mode = ref<'cred' | 'token'>('token')
const credText = ref('')
const token = ref('')
const submission = shallowRef<ImportReceipt | null>(null)
const currentJob = shallowRef<ImportJob | null>(null)
const currentTitle = ref<HTMLHeadingElement | null>(null)
const tokenInput = ref<InstanceType<typeof NInput> | null>(null)
const credInput = ref<InstanceType<typeof NInput> | null>(null)
/** 两种凭据的输入框都常驻（叠放保持高度一致），聚焦时按当前方式挑一个。 */
const focusInput = () => (mode.value === 'token' ? tokenInput : credInput).value?.focus()
/** 导入引导当前在第几步（0 起）；到「回填并导入」时自动聚焦输入框。 */
const importStep = ref(0)
watch(importStep, step => { if (step === 3) void nextTick(focusInput) })
const commandCopied = ref(false)

const passportUrl = 'https://user.hypergryph.com/'
const sklandUrl = 'https://www.skland.com/'
const tokenUrl = 'https://web-api.hypergryph.com/account/info/hg'
const credCommand = `(()=>{const g=k=>localStorage.getItem(k)||'';let t=g('SK_TOKEN_CACHE_KEY');try{t=JSON.parse(t).token||t}catch{};const o=JSON.stringify({cred:g('SK_OAUTH_CRED_KEY'),sign_token:t});copy(o);return o})()`
const credentials = computed(() => parseCredentials(credText.value))
const cred = computed(() => credentials.value.cred)
const sign = computed(() => credentials.value.sign)
const accessToken = computed(() => readAccessToken(token.value))
const credReady = computed(() => Boolean(cred.value && sign.value))
const tokenReady = computed(() => Boolean(accessToken.value))
const canSubmit = computed(() => (mode.value === 'cred' ? credReady.value : tokenReady.value))
const showTokenForm = computed(() => showForm.value && !loadingSavedToken.value && (!hasSavedToken.value || replacingToken.value))
const credHint = computed(() => {
  if (!credText.value.trim()) return ''
  if (!credentials.value.cred && !credentials.value.sign) return '没识别到 cred 与 sign_token，请粘贴整段字典。'
  if (!credentials.value.cred) return '识别到 sign_token，但缺少 cred。'
  if (!credentials.value.sign) return '识别到 cred，但缺少 sign_token。'
  return `已识别 cred（${credentials.value.cred.length} 字符）与 sign_token（${credentials.value.sign.length} 字符），可以提交了。`
})
const currentStatus = computed(() => currentJob.value?.status ?? 'pending')
const recentJobs = computed(() => jobs.value.filter(job => job.id !== submission.value?.id))
/** 侧栏只放概要（库内局数 + 最近一次导入），完整记录在对话框里看。 */
const historyOpen = ref(false)
const latestJob = computed(() => jobs.value[0] ?? null)
function openHistory() {
  historyOpen.value = true
  void loadJobs()
}
const statusLabels = { pending: '等待写入', done: '已写入', failed: '写入失败' }

function statusLabel(status: ImportJob['status']) {
  return statusLabels[status]
}

function waitedSeconds(createdAt: string): number {
  const started = Date.parse(createdAt)
  return Number.isNaN(started) ? 0 : Math.max(0, Math.round((Date.now() - started) / 1000))
}

function waitedText(createdAt: string): string {
  const seconds = waitedSeconds(createdAt)
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.round(seconds / 60)} 分钟`
}

function stalled(job: ImportJob | null | undefined): job is ImportJob {
  return Boolean(job && job.status === 'pending' && job.processed === 0 && waitedSeconds(job.created_at) > 60)
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function peekSignToken(raw: string): string {
  const value = raw.trim()
  if (!value.startsWith('{')) return value
  try {
    const data = JSON.parse(value)
    return asText(data?.token) || asText(data?.sign_token)
  } catch {
    return ''
  }
}

function readCredentials(source: Record<string, unknown>): Credentials {
  const nested = source.data && typeof source.data === 'object' ? source.data as Record<string, unknown> : {}
  const pick = (keys: string[]) => keys.map(key => asText(source[key]) || asText(nested[key])).find(Boolean) ?? ''
  const cached = pick(['SK_TOKEN_CACHE_KEY'])
  const sign = peekSignToken(cached || pick(['sign_token', 'signToken', 'token']))
  return { cred: pick(['cred', 'SK_OAUTH_CRED_KEY']), sign }
}

function scrapeCredentials(text: string): Credentials {
  const find = (keys: string[]) => {
    for (const key of keys) {
      const match = new RegExp(`"?${key}"?\\s*[:=]\\s*"((?:[^"\\\\]|\\\\.)*)"`).exec(text)
      const found = match?.[1]?.replace(/\\"/g, '"').replace(/\s+/g, '') ?? ''
      if (found) return found
    }
    return ''
  }
  const cached = find(['SK_TOKEN_CACHE_KEY'])
  return {
    cred: find(['cred', 'SK_OAUTH_CRED_KEY']),
    sign: peekSignToken(cached) || find(['sign_token', 'signToken', 'token']),
  }
}

function normalizePaste(input: string): string {
  let text = input
    .replace(/[\u200b-\u200d\ufeff\u3000]/g, '')
    .replace(/[“”„‟＂]/g, '"')
    .replace(/[‘’‚‛]/g, "'")
    .replace(/[｛｝]/g, character => (character === '｛' ? '{' : '}'))
    .replace(/[：﹕]/g, ':')
    .replace(/[，、]/g, ',')
    .replace(/[；]/g, ';')
    .trim()
  for (const quote of ['"', "'"]) {
    if (text.length > 1 && text.startsWith(quote) && text.endsWith(quote)) {
      text = text.slice(1, -1).trim()
    }
  }
  return text
}

function parseCredentials(input: string): Credentials {
  const text = normalizePaste(input)
  if (!text) return { cred: '', sign: '' }
  if (text.startsWith('{') || text.startsWith('[')) {
    try {
      const data = JSON.parse(text)
      const list = Array.isArray(data) ? data[0] : data
      if (list && typeof list === 'object') {
        const parsed = readCredentials(list as Record<string, unknown>)
        if (parsed.cred || parsed.sign) return parsed
      }
    } catch {
      // 值里被插入了换行时 JSON 不合法，交给下面的宽松解析
    }
    return scrapeCredentials(text)
  }
  if (text.includes('=')) {
    const pairs: Record<string, string> = {}
    for (const part of text.split(/[;\n&]+/)) {
      const index = part.indexOf('=')
      if (index <= 0) continue
      pairs[part.slice(0, index).trim()] = part.slice(index + 1).replace(/^"|"$/g, '').replace(/\s+/g, '')
    }
    return readCredentials(pairs)
  }
  const parts = text.split(',').map(part => part.replace(/\s+/g, '')).filter(Boolean)
  if (parts.length === 2 && parts.every(part => /^[^"'{};\s=]{6,}$/.test(part))) {
    return { cred: parts[0], sign: parts[1] }
  }
  return { cred: '', sign: '' }
}

let poll: ReturnType<typeof setTimeout> | undefined
let copyTimer: ReturnType<typeof setTimeout> | undefined
let request: AbortController | null = null
const savedTokenRequest = new AbortController()
let hasLoaded = false
let disposed = false

async function loadSavedToken() {
  loadingSavedToken.value = true
  tokenStatusError.value = ''
  try {
    const { saved } = await api<{ saved: boolean }>('/imports/skland/token', { signal: savedTokenRequest.signal })
    if (!disposed) hasSavedToken.value = saved
  } catch (reason) {
    if (!disposed) tokenStatusError.value = `读取保存状态失败。${message(reason)}`
  } finally {
    loadingSavedToken.value = false
  }
}

async function loadTotal() {
  try {
    const page = await api<{ total: number }>('/matches?limit=1&include_exits=true')
    if (!disposed) totalMatches.value = page.total
  } catch {
    // 计数失败不影响导入流程
  }
}

async function loadJobs() {
  if (disposed) return
  clearTimeout(poll)
  request?.abort()
  const controller = new AbortController()
  request = controller
  jobsPending.value = true
  jobsError.value = ''
  try {
    const nextJobs = await api<ImportJob[]>('/imports', { signal: controller.signal })
    if (controller.signal.aborted) return
    const finished = new Set(jobs.value.filter(job => job.status === 'done').map(job => job.id))
    if (nextJobs.some(job => job.status === 'done' && !finished.has(job.id) && (hasLoaded || job.id === submission.value?.id))) {
      refresh()
      void loadTotal()
    }
    const submittedJob = nextJobs.find(job => job.id === submission.value?.id)
    if (submittedJob) currentJob.value = submittedJob
    jobs.value = nextJobs
    hasLoaded = true
  } catch (reason) {
    if (!controller.signal.aborted) jobsError.value = message(reason)
  } finally {
    if (!controller.signal.aborted) {
      jobsPending.value = false
      if ((submission.value && currentStatus.value === 'pending') || jobs.value.some(job => job.status === 'pending')) {
        poll = setTimeout(() => { void loadJobs() }, 2000)
      }
    }
  }
}

function openForm() {
  pullError.value = ''
  pasteHint.value = ''
  autoPulled = ''
  replacingToken.value = false
  showForm.value = true
  importStep.value = 0
}

function replaceToken() {
  pullError.value = ''
  mode.value = 'token'
  replacingToken.value = true
  importStep.value = 1
}

function cancelReplacement() {
  token.value = ''
  credText.value = ''
  openForm()
}

async function clearSavedToken() {
  if (pulling.value || clearingToken.value) return
  pullError.value = ''
  clearingToken.value = true
  try {
    await api('/imports/skland/token', { method: 'DELETE' })
    if (!disposed) {
      hasSavedToken.value = false
      openForm()
    }
  } catch (reason) {
    if (!disposed) pullError.value = `清除 token 失败。${message(reason)}`
  } finally {
    clearingToken.value = false
  }
}

function changeMethod() {
  pullError.value = ''
  pasteHint.value = ''
}

function readAccessToken(input: string): string {
  const value = input.trim()
  if (!value.startsWith('{') && !value.startsWith('[')) return value
  try {
    const data = JSON.parse(value)?.data
    if (typeof data?.content === 'string') return data.content.trim()
    if (typeof data?.token === 'string') return data.token.trim()
  } catch {
    return ''
  }
  return ''
}

function updateToken(value: string) {
  token.value = value
  pullError.value = ''
  pasteHint.value = ''
}

async function pasteToken() {
  if (pasting.value || pulling.value) return
  pasting.value = true
  pasteHint.value = ''
  const previousToken = token.value
  try {
    const copied = (await navigator.clipboard.readText()).trim()
    if (disposed || mode.value !== 'token' || !showForm.value || pulling.value || token.value !== previousToken) return
    if (!copied) {
      pasteHint.value = '剪贴板里没有可粘贴的文字。'
      return
    }
    const value = readAccessToken(copied)
    if (!value) {
      pasteHint.value = '页面没有返回 token。请登录通行证后重新打开 token 页面。'
      return
    }
    token.value = value
    pullError.value = ''
    pasteHint.value = ''
  } catch {
    if (!disposed && mode.value === 'token' && showForm.value) {
      pasteHint.value = '请在输入框内手动粘贴 token。'
      focusInput()
    }
  } finally {
    pasting.value = false
  }
}

async function copyCredCommand() {
  if (copyTimer) clearTimeout(copyTimer)
  try {
    await navigator.clipboard.writeText(credCommand)
    commandCopied.value = true
  } catch {
    commandCopied.value = false
  }
  copyTimer = setTimeout(() => { commandCopied.value = false }, 2400)
}

function updateCredentials(value: string) {
  credText.value = value
  pullError.value = ''
}

async function importFromSkland(useSaved = false) {
  if (pulling.value || clearingToken.value || (useSaved ? !hasSavedToken.value : !canSubmit.value)) return
  pullError.value = ''
  pasteHint.value = ''
  pulling.value = true
  const newToken = !useSaved && mode.value === 'token'
  try {
    const data = useSaved ? { use_saved_token: true }
      : newToken ? { token: accessToken.value }
      : { cred: cred.value, sign_token: sign.value }
    const receipt = await api<ImportReceipt>('/imports/skland', post(data))
    if (disposed) return

    if (receipt.token_saved) {
      hasSavedToken.value = true
      tokenStatusError.value = ''
    }
    currentJob.value = null
    submission.value = receipt
    showForm.value = false
    credText.value = ''
    token.value = ''
    autoPulled = ''
    void loadJobs()
    void nextTick(() => currentTitle.value?.focus())
  } catch (reason) {
    if (disposed) return
    if (reason instanceof ApiError && reason.status < 500) {
      pullError.value = reason.message
      if (useSaved && reason.status === 404) void loadSavedToken()
    } else {
      pullError.value = '未确认导入结果，请先查看最近导入，再决定是否重试。'
      void loadJobs()
    }
  } finally {
    pulling.value = false
  }
}

function credentialSignature(): string {
  return mode.value === 'token' ? `token\n${accessToken.value}` : `cred\n${cred.value}\n${sign.value}`
}

let autoPulled = ''

watch([canSubmit, credentialSignature], () => {
  // 粘贴或填入有效凭据后直接拉取；同一份内容只自动拉一次，失败后交给按钮重试
  if (!showTokenForm.value || pulling.value || !canSubmit.value) return
  const signature = credentialSignature()
  if (!signature || signature === autoPulled) return
  autoPulled = signature
  void importFromSkland()
})

onMounted(() => {
  void loadSavedToken()
  void loadJobs()
  void loadTotal()
})
onBeforeUnmount(() => {
  disposed = true
  clearTimeout(poll)
  clearTimeout(copyTimer)
  request?.abort()
  savedTokenRequest.abort()
})
</script>

<template>
  <div class="import-layout">
    <section class="panel import-panel" aria-labelledby="import-title">
      <header class="import-heading">
        <div class="import-heading-top">
          <h2 id="import-title">从森空岛导入</h2>
          <span class="import-badge">最多 100 局</span>
        </div>
        <p class="muted">同步最近的战绩。重复导入同一局会更新已有记录。</p>
      </header>

      <p v-if="showForm && loadingSavedToken" class="muted" role="status">正在检查已保存的 token…</p>
      <div v-else-if="showForm && hasSavedToken && !replacingToken" class="import-submit saved-token">
        <div>
          <h3>已保存鹰角 token</h3>
          <p class="muted">可以直接同步当前账号的战绩。</p>
        </div>
        <div class="import-submit-action">
          <NButton type="primary" :loading="pulling" :disabled="pulling || clearingToken" @click="importFromSkland(true)">
            {{ pulling ? '正在同步…' : '同步战绩' }}
          </NButton>
          <NButton secondary :disabled="pulling || clearingToken" @click="replaceToken">更换 token</NButton>
          <NButton quaternary :loading="clearingToken" :disabled="pulling || clearingToken" @click="clearSavedToken">清除</NButton>
        </div>
        <p v-if="pullError" class="load-message" role="alert">{{ pullError }}</p>
      </div>

      <form v-else-if="showTokenForm" class="import-form" @submit.prevent="importFromSkland()">
        <p v-if="tokenStatusError" class="load-message" role="status">{{ tokenStatusError }}</p>
        <StepWizard v-model="importStep" :steps="['选择凭据', '登录账号', mode === 'token' ? '复制 token' : '取凭据', '回填并导入']"
          :next-labels="[undefined, '已登录，下一步', mode === 'token' ? '已复制，下一步' : '已复制，下一步']">
          <template #step-0>
            <h3 class="wizard-heading">选择用哪种凭据导入</h3>
            <fieldset class="import-methods" aria-label="凭据类型" :disabled="pulling" @change="changeMethod">
              <label><input v-model="mode" type="radio" name="import-method" value="token">鹰角 access token</label>
              <label><input v-model="mode" type="radio" name="import-method" value="cred">森空岛凭据</label>
            </fieldset>
            <p class="muted">{{ mode === 'token'
              ? '推荐：登录鹰角通行证后复制一段 token，成功后会保存在本站，之后一键同步。'
              : '备用：在森空岛网页的控制台里跑一条命令取 cred 与 sign_token，只在本次请求里使用。' }}</p>
          </template>

          <template #step-1>
            <h3 class="wizard-heading">登录{{ mode === 'token' ? '鹰角通行证' : '森空岛网页版' }}</h3>
            <p class="muted">用要导入战绩的账号登录；已经登录过就直接下一步。</p>
            <div class="wizard-inline-actions">
              <NButton tag="a" type="primary" size="small" :href="mode === 'token' ? passportUrl : sklandUrl"
                target="_blank" rel="noopener noreferrer">{{ mode === 'token' ? '登录通行证' : '打开森空岛' }}</NButton>
            </div>
          </template>

          <template #step-2>
            <div class="mode-stack"><div class="mode-variant" :class="{ 'mode-variant--active': mode === 'token' }" :inert="mode !== 'token' || undefined">
              <h3 class="wizard-heading">打开 token 页面并复制内容</h3>
              <p class="muted">页面会给出整段 JSON，全选复制即可；如果提示未登录，回到上一步登录后再打开。</p>
              <div class="wizard-inline-actions">
                <NButton tag="a" type="primary" size="small" :href="tokenUrl" target="_blank" rel="noopener noreferrer">打开 token 页面</NButton>
              </div>
            </div>
            <div class="mode-variant" :class="{ 'mode-variant--active': mode === 'cred' }" :inert="mode !== 'cred' || undefined">
              <h3 class="wizard-heading">用一条命令取凭据</h3>
              <p class="muted">在森空岛页面按 F12 打开 Console，粘贴这条命令：它读出 cred 与 sign_token，拼成一个字典并复制到剪贴板。</p>
              <figure class="import-cmd">
                <figcaption>DevTools Console</figcaption>
                <pre><code>{{ credCommand }}</code></pre>
              </figure>
              <div class="wizard-inline-actions">
                <NButton type="primary" size="small" @click="copyCredCommand">{{ commandCopied ? '已复制命令' : '复制命令' }}</NButton>
              </div>
              <p class="import-step-note">命令取到空值时，退回 Network 面板任选一条 zonai.skland.com 请求，把请求头里的两项写成 <code>{ "cred": "…", "sign_token": "…" }</code> 也能识别。</p>
            </div></div>
          </template>

          <template #step-3>
            <h3 class="wizard-heading">回填并导入
              <span v-if="canSubmit" class="import-step-state">{{ mode === 'token' ? '已回填' : '已识别' }}</span>
            </h3>
            <div class="mode-stack"><div class="mode-variant" :class="{ 'mode-variant--active': mode === 'token' }" :inert="mode !== 'token' || undefined">
              <p id="import-token-help" class="muted">把复制到的内容粘贴到下面，识别到 token 会自动拉取。</p>
              <div class="token-entry">
                <NInput ref="tokenInput" :value="token" type="password" show-password-on="click" placeholder="粘贴页面内容或 token"
                  :disabled="pulling" :input-props="{ id: 'import-token', autocomplete: 'off', 'aria-describedby': 'import-token-help import-token-safety' }"
                  @update:value="updateToken" />
                <NButton secondary :loading="pasting" :disabled="pulling || pasting" @click="pasteToken">粘贴</NButton>
              </div>
              <p v-if="pasteHint || (token.trim() && !accessToken)" class="import-step-status" data-state="warn" role="status">
                {{ pasteHint || '未识别到 token，请复制 token 页面的完整内容。' }}
              </p>
              <p id="import-token-safety" class="import-step-note">战绩成功拉取并进入写入队列后，鹰角 token 会保存在本站账号中。</p>
            </div>
            <div class="mode-variant" :class="{ 'mode-variant--active': mode === 'cred' }" :inert="mode !== 'cred' || undefined">
              <p id="import-cred-help" class="muted">把上一步复制的字典整段粘贴到下面，识别成功会自动拉取；中文引号、全角逗号、换行会自动纠正。</p>
              <NInput ref="credInput" :value="credText" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder='{"cred":"…","sign_token":"…"}' :disabled="pulling"
                :input-props="{ id: 'import-cred', autocomplete: 'off', spellcheck: 'false', style: 'font-family: ui-monospace, Consolas, monospace; font-size: .9375rem', 'aria-describedby': 'import-cred-help' }"
                @update:value="updateCredentials" />
              <p v-if="credHint" class="import-step-status" :data-state="credReady ? 'ready' : 'warn'" role="status">{{ credHint }}</p>
              <p class="import-step-note">凭据只在本次请求里使用；提交时会发送给本站后端，请仅在自己控制的实例中回填。</p>
            </div></div>
            <p v-if="pullError" class="load-message" role="alert">{{ pullError }}</p>
            <p v-else-if="pulling" class="muted" role="status">正在自动拉取…拉取成功后会进入写入队列。</p>
          </template>

          <template #actions="{ step }">
            <NButton v-if="hasSavedToken" quaternary :disabled="pulling" @click="cancelReplacement">取消更换</NButton>
            <NButton v-if="step === 3" type="primary" attr-type="submit" :loading="pulling" :disabled="!canSubmit || pulling">
              {{ pulling ? '正在拉取…' : pullError ? '重新拉取' : '拉取并导入' }}
            </NButton>
          </template>
        </StepWizard>
      </form>

      <section v-if="submission" class="current-import" aria-labelledby="current-import-title">
        <div class="import-summary">
          <h3 ref="currentTitle" id="current-import-title" tabindex="-1">{{ showForm ? '上次提交' : '本次导入' }}</h3>
          <span class="import-status" :data-status="currentStatus" role="status">{{ statusLabel(currentStatus) }}</span>
        </div>
        <p class="muted">已获取 {{ submission.records ?? submission.total }} 局 · 写入 {{ currentJob?.processed ?? 0 }} / {{ currentJob?.total ?? submission.total }} 局</p>
        <progress v-if="currentStatus === 'pending'" :value="currentJob?.processed ?? 0"
          :max="Math.max(1, currentJob?.total ?? submission.total)" aria-label="本次写入进度"></progress>
        <p v-if="stalled(currentJob)" class="job-stale" role="status">已等待 {{ waitedText(currentJob.created_at) }} 仍无进展：写入进程（worker）可能没在运行。</p>
        <p v-if="currentJob?.error" class="job-error" role="alert">{{ currentJob.error }}</p>
        <div v-if="!showForm || currentStatus === 'done'" class="import-actions">
          <RouterLink v-if="currentStatus === 'done'" to="/matches" custom v-slot="{ href, navigate }">
            <NButton tag="a" :type="showForm ? 'default' : 'primary'" :href="href" @click="navigate">查看对局</NButton>
          </RouterLink>
          <NButton v-if="!showForm" secondary @click="openForm">{{ currentStatus === 'failed' ? '重新拉取' : '再次拉取' }}</NButton>
        </div>
      </section>
    </section>

    <!-- 整块就是一个按钮：点哪里都打开导入记录对话框。按钮里只能放行内元素，所以用 span 排版。 -->
    <section class="panel import-history" aria-labelledby="import-history-title">
      <button type="button" class="history-card" aria-haspopup="dialog" @click="openHistory">
        <span class="history-card-head">
          <span id="import-history-title" class="history-card-title">最近导入</span>
          <span class="history-card-more">{{ jobs.length ? `全部 ${jobs.length} 条` : '查看记录' }}<NIcon :component="ChevronForwardOutline" :size="15" /></span>
        </span>
        <span class="history-facts">
          <span class="history-fact">
            <span class="history-fact-label">库内对局</span>
            <span class="history-fact-value"><b>{{ totalMatches === null ? '—' : totalMatches }}</b><small v-if="totalMatches !== null">局</small></span>
          </span>
          <span class="history-fact">
            <span class="history-fact-label">上次导入</span>
            <span v-if="latestJob" class="history-latest">
              <span><span class="import-status" :data-status="latestJob.status">{{ statusLabel(latestJob.status) }}</span> · 已获取 {{ latestJob.total }} 局</span>
              <time :datetime="latestJob.created_at">{{ dateTime(latestJob.created_at) }}</time>
            </span>
            <span v-else class="history-latest muted">{{ jobsPending ? '读取中…' : '暂无记录' }}</span>
          </span>
        </span>
        <span class="history-note">按局去重计数：同一局重新导入只覆盖字段，不会累加。</span>
      </button>
      <p v-if="jobsError" class="load-message history-error" role="alert">{{ jobsError }}</p>
    </section>

    <NModal v-model:show="historyOpen" preset="card" title="导入记录" class="history-modal" :bordered="false"
      :style="{ width: 'min(560px, calc(100vw - 32px))' }">
      <template #header-extra>
        <NButton size="small" quaternary :loading="jobsPending" @click="loadJobs">刷新</NButton>
      </template>
      <p class="muted history-modal-note">
        <template v-if="totalMatches !== null">库内共 <strong>{{ totalMatches }}</strong> 局（不重复计数）。</template>
        同一局重新导入只覆盖字段，不会累加。
      </p>
      <p v-if="jobsError" class="load-message" role="alert">
        {{ jobsError }} <button type="button" @click="loadJobs">重试</button>
      </p>
      <ul v-if="jobs.length" class="job-list history-list">
        <li v-for="job in jobs" :key="job.id" class="job">
          <span>已获取 {{ job.total }} 局 · <span class="import-status" :data-status="job.status">{{ statusLabel(job.status) }}</span><template v-if="job.status === 'pending'"> · {{ job.processed }} / {{ job.total }}</template></span>
          <time :datetime="job.created_at">{{ dateTime(job.created_at) }}</time>
          <progress v-if="job.status === 'pending'" :value="job.processed" :max="Math.max(1, job.total)" aria-label="写入进度"></progress>
          <span v-if="stalled(job)" class="job-stale">已等待 {{ waitedText(job.created_at) }} 无进展，写入进程（worker）可能没在运行</span>
          <span v-if="job.error" class="job-error">{{ job.error }}</span>
        </li>
      </ul>
      <p v-else-if="jobsPending" class="muted" role="status">正在读取导入记录…</p>
      <p v-else-if="!jobsError" class="muted">还没有导入记录。</p>
    </NModal>
  </div>
</template>

<style scoped>
.import-layout {
  display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr);
  align-items: start; gap: 1rem;
}
.import-panel { display: grid; grid-template-columns: minmax(0, 1fr); gap: .9rem; padding: clamp(.9rem, 2.5vw, 1.4rem); }
.import-panel .load-message, .import-panel .job-list { margin: 0; }
.import-heading { display: grid; gap: .3rem; }
.import-heading-top { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
.import-badge {
  padding: .1rem .5rem; border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
  border-radius: var(--radius); background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent); font-size: .8125rem; font-weight: 600; letter-spacing: .06em;
}
.import-form, .current-import { display: grid; gap: .9rem; }
.wizard-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: .5rem; font-size: 1rem; }
.wizard-inline-actions { display: flex; flex-wrap: wrap; gap: .5rem; }
/* 分段切换：和总览分段卡同一套——整条连在一起，1px 分隔，选中项实色填充 + 深色字。 */
.import-methods {
  display: inline-grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 1px; width: fit-content; max-width: 100%; min-width: 0;
  margin: 0; padding: 0; overflow: hidden; border: 1px solid var(--line); border-radius: var(--radius); background: var(--line);
}
.import-methods label {
  position: relative; display: grid; place-items: center; min-height: 34px; padding: 0 1.1rem;
  background: var(--panel); color: var(--muted); cursor: pointer; font-size: .9375rem; letter-spacing: .04em; white-space: nowrap;
  transition: color .15s, background-color .15s;
}
.import-methods label:hover { background: var(--raised); color: var(--text); }
.import-methods input { position: absolute; width: 1px; height: 1px; clip-path: inset(50%); }
.import-methods label:has(input:checked) { background: var(--accent); color: var(--accent-ink); font-weight: 500; }
.import-methods label:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: -3px; }
.import-methods:disabled label { cursor: default; }
.import-cmd {
  display: grid; margin: .1rem 0 0; border: 1px solid color-mix(in srgb, var(--accent) 32%, var(--line));
  border-radius: var(--radius); background: var(--bg); overflow: hidden;
}
.import-cmd figcaption {
  padding: .3rem .6rem; border-bottom: 1px solid color-mix(in srgb, var(--accent) 26%, var(--line));
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  color: var(--accent); font-size: .8125rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
}
/* 命令只是拿来复制的（旁边有复制按钮），单行横向滚动，不再折成好几行把向导撑高。 */
.import-step-note code { white-space: nowrap; }
.import-cmd pre { margin: 0; padding: .55rem .6rem; overflow-x: auto; scrollbar-width: thin; }
.import-cmd code {
  color: var(--text); font-family: ui-monospace, Consolas, "Cascadia Mono", monospace;
  font-size: .875rem; line-height: 1.65; white-space: pre;
}
/* 两种凭据方式的内容叠在同一格里，只显示当前方式：在第一步切换方式时，向导高度和底部按钮都不动。 */
.mode-stack { display: grid; }
.mode-variant { grid-area: 1 / 1; display: grid; align-content: start; gap: .75rem; min-width: 0; visibility: hidden; }
.mode-variant--active { visibility: visible; }
.token-entry { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: .45rem; }
.import-submit {
  display: flex; align-items: center; justify-content: space-between; gap: .6rem 1rem; flex-wrap: wrap;
  margin-top: .1rem; padding: .7rem .8rem; border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--line));
  border-radius: var(--radius);
  background: linear-gradient(100deg, color-mix(in srgb, var(--accent) 12%, transparent), transparent 72%);
}
.import-submit .muted { font-size: .9375rem; }
.import-submit .load-message { margin: 0; }
.saved-token h3 { margin-bottom: .25rem; }
.saved-token .load-message { flex-basis: 100%; }
.import-submit-action { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
.import-submit-action :deep(.n-button--primary-type) {
  box-shadow: 0 6px 20px color-mix(in srgb, var(--accent) 18%, transparent);
}
.import-actions, .import-summary { display: flex; align-items: center; gap: .55rem; flex-wrap: wrap; }
.import-summary { justify-content: space-between; }
.current-import { border-top: 1px solid var(--line); padding-top: .85rem; }
.import-status { font-weight: 500; color: var(--muted); }
.import-status[data-status='done'] { color: var(--win); }
.import-status[data-status='failed'], .current-import .job-error { color: var(--loss); }
.job progress, .current-import progress { width: 100%; height: .45rem; accent-color: var(--accent); }
.job-stale { color: var(--loss); font-size: .875rem; }
.import-history { padding: 0; overflow: hidden; }
.import-history .history-card {
  display: grid; gap: .85rem; width: 100%; min-height: 0; padding: clamp(.9rem, 2.5vw, 1.4rem);
  border: 0; border-radius: 0; background: transparent; color: var(--text); text-align: left; white-space: normal; cursor: pointer;
  transition: background-color .16s ease;
}
.import-history .history-card:hover:not(:disabled) { background: color-mix(in srgb, var(--text) 4%, var(--panel)); color: var(--text); }
.import-history .history-card:focus-visible { outline-offset: -3px; }
.history-card-head { display: flex; align-items: center; justify-content: space-between; gap: .6rem; }
.history-card-title { font-size: 1.125rem; font-weight: 700; }
.history-card-more { display: inline-flex; align-items: center; gap: .15rem; color: var(--muted); font-size: .9375rem; transition: color .16s ease; }
.history-card-more .n-icon { transition: transform .16s ease; }
.history-card:hover .history-card-more { color: var(--accent); }
.history-card:hover .history-card-more .n-icon { transform: translateX(2px); }
.history-facts { display: grid; gap: 1px; border: 1px solid var(--line); background: var(--line); }
.history-fact { display: grid; gap: .3rem; padding: .7rem .85rem; background: var(--inset); }
.history-fact-label { color: var(--muted); font-size: .9375rem; }
.history-fact-value { display: flex; align-items: baseline; gap: .3rem; }
.history-fact-value b { color: var(--text); font: 700 1.6rem/1 var(--numbers); }
.history-fact-value small { color: var(--muted); font-size: .9375rem; }
.history-latest { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .2rem .6rem; font-size: .9375rem; }
.history-latest time { color: var(--muted); font: .875rem var(--numbers); }
.history-note { color: var(--muted); font-size: .9375rem; line-height: 1.5; }
.history-error { margin: 0 1.4rem 1.2rem; }
.history-modal-note { margin: 0 0 .75rem; font-size: .9375rem; }
.history-modal-note strong { color: var(--accent); font-variant-numeric: tabular-nums; }
/* 记录多时在对话框里滚动，不把对话框撑出屏幕 */
.history-list { max-height: min(60vh, 32rem); overflow-y: auto; overscroll-behavior: contain; }
@media (max-width: 800px) { .import-layout { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 620px) {
  .import-submit { justify-content: stretch; }
  .import-submit-action { justify-content: space-between; width: 100%; }
}
</style>
