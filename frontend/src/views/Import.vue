<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, ApiError, message } from '../api'
import { logbook } from '../context'
import { dateTime } from '../format'
import type { ImportJob } from '../models'

const { refresh } = logbook()
const jobs = ref<ImportJob[]>([])
const importError = ref('')
const jobsError = ref('')
const jobsPending = ref(false)
const importing = ref(false)
const sklandTip = ref('')
const sklandError = ref('')
const sklandMode = ref<'cred' | 'token'>('cred')
const sklandCred = ref('')
const sklandSign = ref('')
const sklandToken = ref('')
let poll: ReturnType<typeof setTimeout> | undefined
let request: AbortController | null = null
let hasLoaded = false
let disposed = false

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
    if (hasLoaded && nextJobs.some(job => job.status === 'done' && !finished.has(job.id))) refresh()
    jobs.value = nextJobs
    hasLoaded = true
  } catch (reason) {
    if (!controller.signal.aborted) jobsError.value = message(reason)
  } finally {
    if (!controller.signal.aborted) {
      jobsPending.value = false
      if (jobs.value.some(job => job.status === 'pending')) {
        poll = setTimeout(() => { void loadJobs() }, 2000)
      }
    }
  }
}

async function importFromSkland() {
  sklandError.value = ''
  sklandTip.value = ''
  const cred = sklandCred.value.trim()
  const sign = sklandSign.value.trim()
  const token = sklandToken.value.trim()
  if (sklandMode.value === 'cred' && (!cred || !sign)) {
    sklandError.value = '请把 cred 与 sign_token 两项都填上。'
    return
  }
  if (sklandMode.value === 'token' && !token) {
    sklandError.value = '请填入鹰角 access token。'
    return
  }
  importing.value = true
  try {
    const job = await api<{ total: number; records: number }>('/imports/skland', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sklandMode.value === 'cred' ? { cred, sign_token: sign } : { token }),
    })
    sklandTip.value = `已拉取 ${job.records ?? job.total} 局，正在写入数据库…`
    await loadJobs()
  } catch (reason) {
    sklandError.value = message(reason)
  } finally {
    importing.value = false
  }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  importError.value = ''
  if (file.size > 8 * 1024 * 1024) {
    importError.value = '战绩文件不能超过 8 MB。'
    return
  }
  importing.value = true
  try {
    const body = await file.text()
    await api('/imports', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    })
  } catch (reason) {
    importError.value = reason instanceof ApiError ? reason.message : '导入失败，请检查文件格式。'
  } finally {
    importing.value = false
    await loadJobs()
  }
}

const statusLabel: Record<ImportJob['status'], string> = { pending: '等待写入', done: '已写入', failed: '写入失败' }

onMounted(() => { void loadJobs() })
onBeforeUnmount(() => {
  disposed = true
  clearTimeout(poll)
  request?.abort()
})
</script>

<template>
  <section class="panel skland-panel">
    <div class="split">
      <h3>从森空岛导入</h3>
      <span class="period">最新 100 局 · 需自备凭据</span>
    </div>
    <p class="muted">服务端只接受显式凭据，不读取任何本机客户端登录态。</p>

    <div class="tabs" role="tablist">
      <button type="button" role="tab" :aria-selected="sklandMode === 'cred'" @click="sklandMode = 'cred'">森空岛凭据</button>
      <button type="button" role="tab" :aria-selected="sklandMode === 'token'" @click="sklandMode = 'token'">鹰角 token</button>
    </div>

    <div v-if="sklandMode === 'cred'" class="skland-form">
      <label>cred
        <NInput v-model:value="sklandCred" placeholder="森空岛 cred（32 位）" :input-props="{ maxlength: 128 }" />
      </label>
      <label>sign_token
        <NInput v-model:value="sklandSign" placeholder="森空岛 sign_token（32 位）" :input-props="{ maxlength: 128 }" />
      </label>
    </div>
    <div v-else class="skland-form">
      <label>鹰角 access token
        <NInput v-model:value="sklandToken" type="textarea" :autosize="{ minRows: 3, maxRows: 5 }"
          placeholder="粘贴鹰角 access token，服务端用它换森空岛凭据" />
      </label>
    </div>

    <div class="skland-actions">
      <NButton type="primary" :loading="importing" @click="importFromSkland">拉取并导入</NButton>
      <span v-if="sklandTip" class="skland-tip">{{ sklandTip }}</span>
      <span v-if="sklandError" class="skland-error" role="alert">{{ sklandError }}</span>
    </div>
    <details class="skland-help">
      <summary>凭据从哪来</summary>
      <p>
        森空岛网页版登录后，请求头里带 <code>cred</code> 与用于签名的 <code>sign_token</code>；
        或者用鹰角通行证导出的 access token，由服务端走 OAuth 换 cred。凭据只在本次请求内使用，不落库。
      </p>
    </details>
  </section>

  <section class="panel import-panel" aria-labelledby="import-title">
    <header class="import-heading">
      <h2 id="import-title">导入战绩</h2>
      <p class="muted">同一局重复导入只会覆盖字段，不会产生重复记录。</p>
    </header>

    <label class="dropzone">
      <input type="file" accept="application/json,.json" :disabled="importing" aria-describedby="import-file-help" @change="upload">
      <strong>{{ importing ? '正在上传…' : '选择战绩 JSON 文件' }}</strong>
      <small id="import-file-help">支持导出的快照（matches 数组）或带干员、装备字典的完整文件，单个文件不超过 8 MB。</small>
    </label>
    <p class="hint">导入在后台写入数据库，完成后总览与对局记录会自动刷新。</p>
    <p v-if="importError" class="load-message" role="alert">{{ importError }}</p>

    <section class="import-history" aria-labelledby="import-history-title">
      <h3 id="import-history-title">最近导入</h3>
      <p v-if="jobsError" class="load-message" role="alert">
        {{ jobsError }} <button type="button" @click="loadJobs">重试</button>
      </p>
      <ul v-if="jobs.length" class="job-list">
        <li v-for="job in jobs" :key="job.id" class="job">
          <span>{{ statusLabel[job.status] }} · {{ job.processed }} / {{ job.total }} 局</span>
          <time :datetime="job.created_at">{{ dateTime(job.created_at) }}</time>
          <progress v-if="job.status === 'pending'" :value="job.processed" :max="Math.max(1, job.total)" aria-label="写入进度"></progress>
          <span v-if="job.error" class="job-error">{{ job.error }}</span>
        </li>
      </ul>
      <p v-else-if="jobsPending" class="muted" role="status">正在读取导入记录…</p>
      <p v-else-if="!jobsError" class="muted">还没有导入记录。</p>
    </section>
  </section>
</template>

<style scoped>
.skland-panel { padding: 1.1rem 1.25rem; display: grid; gap: .55rem; margin-bottom: 1rem; }
.skland-panel .row-actions { display: flex; align-items: center; gap: .75rem; }
.import-panel { display: grid; gap: .85rem; padding: clamp(.9rem, 2.5vw, 1.4rem); }
.import-heading, .import-history { display: grid; gap: .4rem; }
.import-history { border-top: 1px solid var(--line); padding-top: .85rem; }
.import-panel .load-message, .import-panel .job-list { margin: 0; }
.job progress { flex-basis: 100%; height: .45rem; accent-color: var(--accent); }

.skland-panel { padding: 1.1rem 1.25rem; display: grid; gap: .7rem; margin-bottom: 1rem; }
.skland-panel .tabs { display: flex; gap: .5rem; flex-wrap: wrap; }
.skland-panel .tabs button {
  padding: .35rem .8rem; border-radius: 999px; border: 1px solid var(--control-line);
  background: var(--inset); color: var(--muted); cursor: pointer; font: inherit; font-size: .8125rem;
}
.skland-panel .tabs button[aria-selected='true'] { border-color: var(--accent); color: var(--accent); }
.skland-form { display: grid; gap: .55rem; max-width: 42rem; }
.skland-form label { display: grid; gap: .3rem; color: var(--muted); font-size: .8125rem; }
.skland-form :deep(.n-input) { width: 100%; }
.skland-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; }
.skland-tip { color: var(--muted); font-size: .8125rem; }
.skland-error { color: #ff8a80; font-size: .8125rem; }
.skland-help { color: var(--muted); font-size: .78rem; }
.skland-help summary { cursor: pointer; color: var(--accent); }
.skland-help p { margin: .4rem 0 0; line-height: 1.7; }
.skland-help code { background: var(--inset); border: 1px solid var(--line); border-radius: 4px; padding: 0 .2rem; }
</style>
