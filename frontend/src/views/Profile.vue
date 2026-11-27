<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { NButton, NIcon, NInput } from 'naive-ui'
import { CreateOutline } from '@vicons/ionicons5'
import { logbook } from '../context'
import { api, message, send, useResource } from '../api'
import { number } from '../format'
import type { ProfileInfo, User } from '../models'

// 个人主页只负责账号资料：昵称与头像可改，登录名不可改；战绩数据都在战绩总览。
const { revision, user, setUser } = logbook()
const { data, error, refresh } = useResource<ProfileInfo>(ref('/profile'), revision, true)

// 昵称和头像以页头共享的登录态为准，改完立即同步到页头。
const username = computed(() => user.value?.username ?? data.value?.username ?? '')
const displayName = computed(() => user.value?.display_name || username.value)
const avatarUrl = computed(() => user.value?.avatar_url ?? null)
const initial = computed(() => Array.from(displayName.value)[0]?.toUpperCase() ?? '?')
const account = computed(() => data.value?.account ?? null)

const NAME_LIMIT = 16
const editing = ref(false)
const draft = ref('')
const saving = ref(false)
const nameError = ref('')
const nameInput = ref<InstanceType<typeof NInput> | null>(null)

function startEdit() {
  draft.value = user.value?.display_name ?? ''
  nameError.value = ''
  editing.value = true
  void nextTick(() => nameInput.value?.focus())
}

async function saveName() {
  saving.value = true
  nameError.value = ''
  try {
    setUser(await api<User>('/profile', send('PATCH', { display_name: draft.value })))
    editing.value = false
  } catch (reason) {
    nameError.value = message(reason)
  } finally {
    saving.value = false
  }
}

const AVATAR_LIMIT = 2 * 1024 * 1024
const AVATAR_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
const fileInput = ref<HTMLInputElement | null>(null)
const avatarBusy = ref(false)
const avatarError = ref('')

async function uploadAvatar(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  avatarError.value = ''
  if (!AVATAR_TYPES.includes(file.type)) {
    avatarError.value = '只支持 PNG、JPEG、WebP 或 GIF 图片。'
    return
  }
  if (file.size > AVATAR_LIMIT) {
    avatarError.value = '图片不能超过 2 MB。'
    return
  }
  avatarBusy.value = true
  try {
    setUser(await api<User>('/profile/avatar', { method: 'PUT', headers: { 'Content-Type': file.type }, body: file }))
  } catch (reason) {
    avatarError.value = message(reason)
  } finally {
    avatarBusy.value = false
  }
}

async function removeAvatar() {
  avatarBusy.value = true
  avatarError.value = ''
  try {
    setUser(await api<User>('/profile/avatar', send('DELETE')))
  } catch (reason) {
    avatarError.value = message(reason)
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
      <p v-if="nameError || avatarError" class="profile-error" role="alert">{{ nameError || avatarError }}</p>

      <dl class="profile-facts">
        <div><dt>登录账号</dt><dd>{{ username }}<small class="muted">用于登录，不可修改</small></dd></div>
        <div v-if="account?.nickname">
          <dt>游戏昵称</dt>
          <dd>
            {{ account.nickname }}<template v-if="account.nick_number">#{{ account.nick_number }}</template>
            <small v-if="account.level" class="muted">博士等级 {{ account.level }} · 获赞 {{ number(account.likes ?? null) }}</small>
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
  border: 0; border-radius: 0; cursor: pointer;
  clip-path: polygon(30% 0, 70% 0, 100% 30%, 100% 70%, 70% 100%, 30% 100%, 0 70%, 0 30%);
  background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 35%, var(--panel)));
}
.profile-emblem > :is(span, img) {
  display: grid; place-items: center; width: 98px; height: 98px;
  clip-path: inherit; background: var(--inset); object-fit: cover;
  color: var(--accent); font: 800 2.6rem/1 var(--numbers);
}
.profile-emblem-hint {
  position: absolute; inset: 3px; display: grid; place-items: center;
  clip-path: inherit; background: #0b0e13b3; color: #f3f4f6; font-size: .85rem; font-style: normal;
  opacity: 0; transition: opacity .18s ease;
}
.profile-emblem:is(:hover, :focus-visible) .profile-emblem-hint, .profile-emblem--busy .profile-emblem-hint { opacity: 1; }
.profile-emblem:focus-visible { outline: none; filter: drop-shadow(0 0 3px var(--accent)); }
.profile-link { padding: 0; border: 0; background: none; color: var(--muted); font-size: .75rem; cursor: pointer; }
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
.profile-error { color: var(--loss); font-size: .85rem; }

.profile-facts { display: grid; gap: .4rem; margin: 0; }
.profile-facts > div { display: grid; grid-template-columns: 5rem minmax(0, 1fr); align-items: baseline; gap: .75rem; }
.profile-facts dt { color: var(--muted); font-size: .85rem; }
.profile-facts dd { display: flex; flex-wrap: wrap; align-items: baseline; gap: .25rem .75rem; margin: 0; font-weight: 600; }
.profile-facts small { font-weight: 400; font-size: .78rem; }
.profile-bind a, .profile-tip a { color: var(--accent); margin: 0 .15rem; }
.profile-tip { margin-top: .75rem; font-size: .8rem; }

@media (max-width: 560px) {
  .profile-id { grid-template-columns: 1fr; justify-items: start; padding: 1.25rem; }
}
</style>
