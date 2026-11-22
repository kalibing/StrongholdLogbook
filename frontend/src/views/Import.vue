<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, ApiError, message } from '../api'
import { logbook } from '../context'
import { dateTime } from '../format'
import type { ImportJob } from '../models'

const { refresh } = logbook()
const jobs = ref<ImportJob[]>([])
const importError = ref('')
const importing = ref(false)
let poll: ReturnType<typeof setTimeout> | undefined
let lastDone = ''

const pendingJobs = computed(() => jobs.value.filter(job => job.status === 'pending'))

async function loadJobs() {
  try {
    jobs.value = await api<ImportJob[]>('/imports')
  } catch (reason) {
    importError.value = message(reason)
    return
  }
  schedulePoll()
}

function schedulePoll() {
  if (poll) clearTimeout(poll)
  if (!pendingJobs.value.length) return
  poll = setTimeout(() => { void loadJobs() }, 2000)
}

function noteFinished() {
  const done = jobs.value.filter(job => job.status === 'done').map(job => job.id).join(',')
  if (!done) return
  if (!lastDone) { lastDone = done; return }
  if (done === lastDone) return
  lastDone = done
  refresh()
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

watch(jobs, noteFinished)
onMounted(() => { void loadJobs() })
onBeforeUnmount(() => { if (poll) clearTimeout(poll) })
</script>

<template>
  <section class="panel import-panel" aria-labelledby="import-title">
    <div class="split">
      <div>
        <h2 id="import-title">导入战绩</h2>
        <p class="muted">同一局重复导入只会覆盖字段，不会产生重复记录。</p>
      </div>
    </div>

    <label class="dropzone">
      <input type="file" accept="application/json,.json" :disabled="importing" @change="upload">
      <strong>{{ importing ? '正在上传…' : '选择战绩 JSON 文件' }}</strong>
      <small>支持导出的快照（matches 数组）或带干员、装备字典的完整文件，单个文件不超过 8 MB。</small>
    </label>
    <p class="hint">导入在后台写入数据库，完成后总览与对局记录会自动刷新。</p>
    <p v-if="importError" class="load-message" role="alert">{{ importError }}</p>

    <h3>最近导入</h3>
    <ul v-if="jobs.length" class="job-list">
      <li v-for="job in jobs" :key="job.id" class="job">
        <span>{{ statusLabel[job.status] }} · {{ job.processed }} / {{ job.total }} 局</span>
        <time :datetime="job.created_at">{{ dateTime(job.created_at) }}</time>
        <span v-if="job.error" class="job-error">{{ job.error }}</span>
      </li>
    </ul>
    <p v-else class="muted">还没有导入记录。</p>
  </section>
</template>
