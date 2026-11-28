<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { NButton, NIcon, NInput, useMessage } from 'naive-ui'
import { CreateOutline } from '@vicons/ionicons5'
import { logbook } from '../context'
import { api, message, post, send, useResource } from '../api'
import { number } from '../format'
import type { ProfileInfo, User } from '../models'

// 个人主页只负责账号资料：昵称与头像可改；登录名一般不可改，QQ 机器人注册的账号可以改一次。
const { revision, user, setUser } = logbook()
const { data, error, refresh } = useResource<ProfileInfo>(ref('/profile'), revision, true)
// 操作结果（保存失败、复制结果等）用 toast 提示；页面数据读取失败仍在原位显示并可重试。
const toast = useMessage()

// 昵称和头像以页头共享的登录态为准，改完立即同步到页头。
const username = computed(() => user.value?.username ?? data.value?.username ?? '')
const displayName = computed(() => user.value?.display_name || username.value)
const avatarUrl = computed(() => user.value?.avatar_url ?? null)
const initial = computed(() => Array.from(displayName.value)[0]?.toUpperCase() ?? '?')
const account = computed(() => data.value?.account ?? null)
const qq = computed(() => data.value?.qq ?? null)
const qqBinding = ref<{ command: string; expires_in: number } | null>(null)
const qqBusy = ref(false)

async function requestQqBinding() {
  qqBusy.value = true
  try {
    qqBinding.value = await api('/profile/qq-binding', post({}))
  } catch (reason) {
    toast.error(message(reason))
    refresh()
  } finally {
    qqBusy.value = false
  }
}

async function copyQqCommand() {
  if (!qqBinding.value) return
  try {
    await navigator.clipboard.writeText(qqBinding.value.command)
    toast.success('已复制')
  } catch {
    toast.warning('无法自动复制，请手动复制指令')
  }
}

const NAME_LIMIT = 16
const editing = ref(false)
const draft = ref('')
const saving = ref(false)
const nameInput = ref<InstanceType<typeof NInput> | null>(null)

function startEdit() {
  draft.value = user.value?.display_name ?? ''
  editing.value = true
  void nextTick(() => nameInput.value?.focus())
}

async function saveName() {
  saving.value = true
  try {
    setUser(await api<User>('/profile', send('PATCH', { display_name: draft.value })))
    editing.value = false
  } catch (reason) {
    toast.error(message(reason))
  } finally {
    saving.value = false
  }
}

const USERNAME_RULE = /^[a-z0-9][a-z0-9_.-]{2,63}$/
const canRename = computed(() => user.value?.username_editable === true)
const renaming = ref(false)
const renameDraft = ref('')
const renameBusy = ref(false)

function startRename() {
  renameDraft.value = ''
  renaming.value = true
}

async function saveRename() {
  const value = renameDraft.value.trim().toLowerCase()
  if (!USERNAME_RULE.test(value)) {
    toast.error('账号须为 3–64 位小写字母、数字、点、下划线或连字符，且以字母或数字开头')
    return
  }
  if (value.startsWith('qq-')) {
    toast.error('新账号不能以 qq- 开头')
    return
  }
  if (!window.confirm(`把登录账号改为「${value}」？只能修改这一次，之后用新账号和原密码登录。`)) return
  renameBusy.value = true
  try {
    setUser(await api<User>('/account/username', send('PATCH', { username: value })))
    renaming.value = false
  } catch (reason) {
    toast.error(message(reason))
  } finally {
    renameBusy.value = false
  }
}

const AVATAR_LIMIT = 2 * 1024 * 1024
const AVATAR_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
const fileInput = ref<HTMLInputElement | null>(null)
const avatarBusy = ref(false)

async function uploadAvatar(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!AVATAR_TYPES.includes(file.type)) {
    toast.error('只支持 PNG、JPEG、WebP 或 GIF 图片。')
    return
  }
  if (file.size > AVATAR_LIMIT) {
    toast.error('图片不能超过 2 MB。')
    return
  }
  avatarBusy.value = true
  try {
    setUser(await api<User>('/profile/avatar', { method: 'PUT', headers: { 'Content-Type': file.type }, body: file }))
  } catch (reason) {
    toast.error(message(reason))
  } finally {
    avatarBusy.value = false
  }
}

async function removeAvatar() {
  avatarBusy.value = true
  try {
    setUser(await api<User>('/profile/avatar', send('DELETE')))
  } catch (reason) {
    toast.error(message(reason))
  } finally {
    avatarBusy.value = false
  }
}
</script>

<template>
  <section class="panel profile-id" aria-labelledby="profile-name">
    <div class="profile-avatar">
      <button type="button" class="profile-emblem" :class="{ 'profile-emblem--busy': avatarBusy }" :disabled="avatarBusy"
        title="更换头像" aria-label="更换头像" @click="fileInput?.click()">
        <img v-if="avatarUrl" :src="avatarUrl" alt="">
        <span v-else aria-hidden="true">{{ initial }}</span>
        <i class="profile-emblem-hint" aria-hidden="true">{{ avatarBusy ? '处理中' : '更换' }}</i>
      </button>
      <input ref="fileInput" type="file" :accept="AVATAR_TYPES.join(',')" hidden @change="uploadAvatar">
      <button v-if="avatarUrl" type="button" class="profile-link" :disabled="avatarBusy" @click="removeAvatar">移除头像</button>
    </div>

    <div class="profile-who">
      <h2 v-if="!editing" id="profile-name" class="profile-name">
        <span>{{ displayName }}</span>
        <button type="button" class="profile-edit" title="修改昵称" aria-label="修改昵称" @click="startEdit">
          <NIcon :component="CreateOutline" :size="18" />
        </button>
      </h2>
      <form v-else class="profile-name-form" @submit.prevent="saveName" @keydown.esc="editing = false">
        <NInput ref="nameInput" v-model:value="draft" size="small" :maxlength="NAME_LIMIT" show-count clearable
          placeholder="留空则显示账号名" aria-label="昵称" />
        <NButton size="small" type="primary" attr-type="submit" :loading="saving">保存</NButton>
        <NButton size="small" secondary :disabled="saving" @click="editing = false">取消</NButton>
      </form>

      <dl class="profile-facts">
        <div>
          <dt>登录账号</dt>
          <dd v-if="!renaming">
            {{ username }}
            <small v-if="canRename" class="muted">
              QQ 机器人生成的账号，可以改一次
              <button type="button" class="profile-link" @click="startRename">修改账号</button>
            </small>
            <small v-else class="muted">用于登录，不可修改</small>
          </dd>
          <dd v-else>
            <form class="profile-name-form" @submit.prevent="saveRename" @keydown.esc="renaming = false">
              <NInput v-model:value="renameDraft" size="small" :maxlength="64" placeholder="新的登录账号" aria-label="新的登录账号"
                :input-props="{ autocapitalize: 'off', spellcheck: false, autocomplete: 'username' }" />
              <NButton size="small" type="primary" attr-type="submit" :loading="renameBusy">保存</NButton>
              <NButton size="small" secondary :disabled="renameBusy" @click="renaming = false">取消</NButton>
            </form>
            <small class="muted">只能修改一次，密码不变。</small>
          </dd>
        </div>
        <div v-if="account?.nickname">
          <dt>游戏昵称</dt>
          <dd>
            {{ account.nickname }}<template v-if="account.nick_number">#{{ account.nick_number }}</template>
            <small v-if="account.level" class="muted">博士等级 {{ account.level }} · 获赞 {{ number(account.likes ?? null) }}</small>
          </dd>
        </div>
        <div v-if="qq">
          <dt>QQ 账号</dt>
          <dd>
            <template v-if="qq.bound">
              已绑定 <small class="muted">可以私聊机器人发「登录」获取网页登录链接。</small>
            </template>
            <template v-else>
              <NButton size="small" secondary :loading="qqBusy" @click="requestQqBinding">
                {{ qqBinding ? '重新获取绑定码' : '获取 QQ 绑定码' }}
              </NButton>
              <div v-if="qqBinding" class="profile-qq-binding">
                <small class="muted">请在 {{ qqBinding.expires_in / 60 }} 分钟内私聊机器人发送下面的完整指令。</small>
                <div class="profile-qq-command">
                  <code>{{ qqBinding.command }}</code>
                  <NButton size="small" secondary @click="copyQqCommand">复制</NButton>
                </div>
                <NButton size="small" text @click="refresh">我已发送，刷新状态</NButton>
              </div>
            </template>
            <small class="muted profile-qq-group">在群里 @机器人 发「{{ qq.report_command }}」查询昨日战报、发「{{ qq.record_command }}」查询最近 10 局战绩：第一次会私聊你一个关联链接，打开并确认即可，不需要先绑定 QQ。</small>
          </dd>
        </div>
      </dl>
      <p v-if="data && !account" class="profile-bind muted">
        绑定<RouterLink to="/achievements">成就档案</RouterLink>后可在这里看到游戏昵称与博士等级。
      </p>
      <p v-if="error" class="profile-error" role="alert">
        {{ error }} <button type="button" class="profile-link" @click="refresh">重试</button>
      </p>
    </div>
  </section>
  <p class="profile-tip muted">头像支持 PNG / JPEG / WebP / GIF，最大 2 MB，会居中裁成正方形。战绩数据请到<RouterLink to="/">战绩总览</RouterLink>查看。</p>
</template>

<style scoped>
.profile-id {
  position: relative; overflow: hidden;
  display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 1.5rem;
  padding: 1.5rem 1.75rem;
}
.profile-id::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--accent); }

.profile-avatar { display: grid; justify-items: center; gap: .4rem; }
.profile-emblem {
  position: relative; display: grid; place-items: center; width: 104px; height: 104px; flex: none; padding: 0;
  border: 0; border-radius: 50%; cursor: pointer;
  clip-path: circle(50%);
  background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 35%, var(--panel)));
}
.profile-emblem > :is(span, img) {
  display: grid; place-items: center; width: 98px; height: 98px;
  clip-path: inherit; background: var(--inset); object-fit: cover;
  color: var(--accent); font: 800 2.6rem/1 var(--numbers);
}
.profile-emblem-hint {
  position: absolute; inset: 3px; display: grid; place-items: center;
  clip-path: inherit; background: #0a0f0cb3; color: #f3f4f6; font-size: .9375rem; font-style: normal;
  opacity: 0; transition: opacity .18s ease;
}
.profile-emblem:is(:hover, :focus-visible) .profile-emblem-hint, .profile-emblem--busy .profile-emblem-hint { opacity: 1; }
.profile-emblem:focus-visible { outline: none; filter: drop-shadow(0 0 3px var(--accent)); }
.profile-link { padding: 0; border: 0; background: none; color: var(--muted); font-size: .875rem; cursor: pointer; }
.profile-link:hover { color: var(--loss); }

.profile-who { display: grid; gap: .55rem; min-width: 0; }
.profile-name { display: flex; align-items: center; gap: .4rem; min-width: 0; font-size: 1.7rem; }
.profile-name span { overflow-wrap: anywhere; }
.profile-edit {
  display: inline-grid; place-items: center; width: 32px; height: 32px; flex: none; padding: 0;
  border: 1px solid transparent; border-radius: 2px; background: none; color: var(--muted); cursor: pointer;
}
.profile-edit:hover, .profile-edit:focus-visible { color: var(--accent); border-color: var(--line); }
.profile-name-form { display: flex; align-items: center; gap: .5rem; max-width: 26rem; min-height: 2.6rem; }
.profile-name-form .n-input { flex: 1; }
.profile-error { color: var(--loss); font-size: .9375rem; }

.profile-facts { display: grid; gap: .4rem; margin: 0; }
.profile-facts > div { display: grid; grid-template-columns: 4rem minmax(0, 1fr); align-items: baseline; gap: .75rem; }
.profile-facts dt { color: var(--muted); font-size: .9375rem; }
.profile-facts dd { display: flex; flex-wrap: wrap; align-items: baseline; gap: .25rem .75rem; margin: 0; font-weight: 500; }
.profile-facts small { font-weight: 400; font-size: .9375rem; }
.profile-qq-group { display: block; flex-basis: 100%; margin-top: .35rem; }
.profile-qq-binding { display: grid; justify-items: start; gap: .45rem; flex-basis: 100%; min-width: 0; }
.profile-qq-command { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
.profile-qq-command code { padding: .25rem .45rem; background: var(--inset); overflow-wrap: anywhere; }
.profile-bind a, .profile-tip a { color: var(--accent); margin: 0 .15rem; }
.profile-tip { margin-top: .75rem; font-size: .9375rem; }

@media (max-width: 560px) {
  .profile-id { grid-template-columns: 1fr; justify-items: start; padding: 1.25rem; }
}
</style>
