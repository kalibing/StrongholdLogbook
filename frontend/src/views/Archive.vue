<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, ApiError, message, post } from '../api'
import { logbook } from '../context'
import { dateTime } from '../format'
import type { ImportJob } from '../models'

const { role, roles, createRole, renameRole, deleteRole, selectRole, refresh } = logbook()

const name = ref('')
const creating = ref(false)
const createError = ref('')

const editingId = ref('')
const editingName = ref('')
const actionError = ref('')
const confirmingId = ref('')

const jobs = ref<ImportJob[]>([])
const importError = ref('')
const importing = ref(false)
let poll: ReturnType<typeof setTimeout> | undefined
let lastDone = ''

const pendingJobs = computed(() => jobs.value.filter(job => job.status === 'pending'))

async function submitRole() {
  createError.value = ''
  creating.value = true
  try {
    await createRole(name.value.trim())
    name.value = ''
  } catch (reason) {
    createError.value = message(reason)
  } finally {
    creating.value = false
  }
}

function startRename(id: string, current: string) {
  editingId.value = id
  editingName.value = current
  actionError.value = ''
}

async function saveRename(id: string) {
  actionError.value = ''
  try {
    await renameRole(id, editingName.value.trim())
    editingId.value = ''
  } catch (reason) {
    actionError.value = message(reason)
  }
}

async function removeRole(id: string) {
  actionError.value = ''
  if (confirmingId.value !== id) {
    confirmingId.value = id
    return
  }
  try {
    await deleteRole(id)
    confirmingId.value = ''
    if (!roles.value.length) jobs.value = []
  } catch (reason) {
    actionError.value = message(reason)
  }
}

async function loadJobs() {
  if (!role.value) { jobs.value = []; return }
  try {
    jobs.value = await api<ImportJob[]>('/roles/' + role.value.id + '/imports')
  } catch (reason) {
    importError.value = message(reason)
    return
  }
  schedulePoll()
}

function schedulePoll() {
  if (poll) clearTimeout(poll)
  if (!pendingJobs.value.length) return
  poll = setTimeout(() => { void loadJobs() }, 2500)
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
  if (!file || !role.value) return
  importError.value = ''
  if (file.size > 8 * 1024 * 1024) {
    importError.value = '战绩文件不能超过 8 MB。'
    return
  }
  importing.value = true
  try {
    const body = await file.text()
    await api('/roles/' + role.value.id + '/imports', {
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
watch(role, () => {
  jobs.value = []
  importError.value = ''
  confirmingId.value = ''
  editingId.value = ''
  void loadJobs()
})
onMounted(() => { void loadJobs() })
onBeforeUnmount(() => { if (poll) clearTimeout(poll) })
</script>

<template>
  <div class="archive-grid">
    <section class="panel" aria-labelledby="role-title">
      <div class="split">
        <h2 id="role-title">角色档案</h2>
        <span class="period">{{ roles.length }} 个档案</span>
      </div>

      <form @submit.prevent="submitRole">
        <label class="filter-field">新建档案名称
          <input v-model="name" required maxlength="60" placeholder="例如：主号">
        </label>
        <p class="hint">档案用于区分同一账号下的不同角色，名称最多 60 个字符。</p>
        <p v-if="createError" class="load-message" role="alert">{{ createError }}</p>
        <button type="submit" class="login-submit" :disabled="creating || !name.trim()">{{ creating ? '创建中…' : '创建档案' }}</button>
      </form>

      <div v-if="roles.length" class="role-list">
        <div v-for="item in roles" :key="item.id" class="role-item" :class="{ active: item.id === role?.id }">
          <template v-if="editingId === item.id">
            <input v-model="editingName" maxlength="60" aria-label="新的档案名称">
            <span class="role-actions">
              <button type="button" @click="saveRename(item.id)" :disabled="!editingName.trim()">保存</button>
              <button type="button" @click="editingId = ''">取消</button>
            </span>
          </template>
          <template v-else>
            <strong>{{ item.name }}</strong>
            <span class="role-actions">
              <button type="button" @click="selectRole(item.id)" :disabled="item.id === role?.id">切换</button>
              <button type="button" @click="startRename(item.id, item.name)">重命名</button>
              <button type="button" class="danger" @click="removeRole(item.id)">
                {{ confirmingId === item.id ? '确认删除' : '删除' }}
              </button>
            </span>
          </template>
        </div>
      </div>
      <p v-else class="muted">还没有档案，先创建一个再导入战绩。</p>
      <p v-if="actionError" class="load-message" role="alert">{{ actionError }}</p>
    </section>

    <section class="panel" aria-labelledby="import-title">
      <div class="split">
        <h2 id="import-title">导入战绩</h2>
        <span class="period">{{ role ? role.name : '未选择档案' }}</span>
      </div>

      <template v-if="role">
        <label class="dropzone">
          <input type="file" accept="application/json,.json" :disabled="importing" @change="upload">
          <strong>{{ importing ? '正在上传…' : '选择战绩 JSON 文件' }}</strong>
          <small>支持导出的快照（matches 数组）或带干员、装备字典的完整文件，单个文件不超过 8 MB。</small>
        </label>
        <p class="hint">导入在后台写入数据库，完成后总览与对局记录会自动刷新；重复导入同一局不会产生重复记录。</p>
        <p v-if="importError" class="load-message" role="alert">{{ importError }}</p>

        <h3>最近导入</h3>
        <ul v-if="jobs.length" class="job-list">
          <li v-for="job in jobs" :key="job.id" class="job">
            <span>{{ statusLabel[job.status] }} · {{ job.processed }} / {{ job.total }} 局</span>
            <time :datetime="job.created_at">{{ dateTime(job.created_at) }}</time>
            <span v-if="job.error" class="job-error">{{ job.error }}</span>
          </li>
        </ul>
        <p v-else class="muted">这个档案还没有导入记录。</p>
      </template>
      <p v-else class="muted">先创建或切换一个角色档案，然后再导入战绩文件。</p>
    </section>
  </div>
</template>
