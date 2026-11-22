<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { NButton, NInput, NSpin, useMessage } from 'naive-ui'
import { api, ApiError, message, post } from '../api'
import AchievementRadar from '../components/AchievementRadar.vue'
import type { AchvBadge, AchvBandTop, AchvEnvelope, AchvProfile, AchvState, AchvTitle } from '../models'

const notify = useMessage()
const state = ref<AchvState | null>(null)
const profile = ref<AchvProfile | null>(null)
const warning = ref('')
const pending = ref(true)
const busy = ref(false)
const mode = ref<'web' | 'hypergryph' | 'token'>('token')
const phone = ref('')
const password = ref('')
const token = ref('')
const formError = ref('')
const webState = ref<'idle' | 'waiting' | 'syncing' | 'done'>('idle')
let pollTimer: number | undefined

const connected = computed(() => Boolean(state.value?.connected && profile.value))
const fetched = computed(() => {
  const value = profile.value?.fetched_at
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
})
const teammate = computed(() => profile.value?.social.best_teammate ?? null)

const overviewTitles = computed(() => groupTitles('overview'))
const specialTitles = computed(() => groupTitles('special'))
function groupTitles(group: 'overview' | 'special') {
  const rows = (profile.value?.titles ?? []).filter(t => t.group === group)
  return rows.sort((a, b) => a.type.localeCompare(b.type) || a.rank - b.rank)
}
function titleIconUrl(title: AchvTitle) {
  return '/art/titles/' + title.id + '.png'
}
function hideOnError(event: Event) {
  const image = event.target as HTMLImageElement
  image.style.visibility = 'hidden'
}

const badgeList = computed(() => profile.value?.bands.badges ?? [])

function avatarUrl(value: string | null): string {
  if (!value) return '/portraits/char_010_chen.png'
  return '/portraits/' + value.split('#')[0] + '.png'
}
function avatarFallback(event: Event, value: string | null) {
  const image = event.target as HTMLImageElement
  if (!value || image.dataset.fallback) return
  image.dataset.fallback = '1'
  // char_xxx#N 走皮肤头像目录，avatar_special_xx 走通用头像目录，两者不能混
  image.src = value.startsWith('avatar_')
    ? 'https://web.hycdn.cn/arknights/game/assets/avatar/' + encodeURIComponent(value) + '.png'
    : 'https://web.hycdn.cn/arknights/game/assets/char_skin/avatar/' + encodeURIComponent(value) + '.png'
}
function nameCardLocal(value: string): string {
  return `/art/namecards/${value}.png`
}
function nameCardFallback(event: Event, value: string | null) {
  const image = event.target as HTMLImageElement
  if (!value || image.dataset.fallback) {
    image.hidden = true
    return
  }
  image.dataset.fallback = '1'
  image.src = `https://web.hycdn.cn/arknights/game/assets/name_card/short/${encodeURIComponent(value)}.png`
}
function bandFallback(event: Event, band: AchvBandTop) {
  const image = event.target as HTMLImageElement
  if (image.dataset.fallback) return
  image.dataset.fallback = '1'
  image.src = 'https://web.hycdn.cn/arknights/game/assets/auto_chess/band_icon/' + band.id + '.png'
}
function badgeUrl(badge: AchvBadge): string {
  return '/art/strategy-' + badge.id + '.png'
}
// 右上角那枚「特殊策略标识」角标：来自卫戍协议 H5 的 mark_pro（青绿虹彩）；
// 未精通态在游戏里是暖橙，用同一张图压色相得到。
function markUrl(badge: AchvBadge): string {
  return badge.obtained ? '/art/achv-mark-pro.png' : '/art/achv-mark-pro-orange.png'
}
function badgeFallback(event: Event, badge: AchvBadge) {
  const image = event.target as HTMLImageElement
  if (!badge.icon || image.dataset.fallback) return
  image.dataset.fallback = '1'
  image.src = badge.icon
}
const trophyIcon = computed(() => {
  const level = profile.value?.trophy.level ?? 1
  return level >= 8 ? '/art/trophy_level8_icon.png' : ''
})
// 已获赞的图：取自卫戍协议 H5 里 .GMDJVs .VMRzld 的点赞框图（base64 已落盘为 png）
const likeIcon = '/art/like-box.png'

async function load() {
  pending.value = true
  formError.value = ''
  try {
    const status = await api<AchvState>('/achv/status')
    state.value = status
    if (!status.connected) {
      profile.value = null
      return
    }
    const envelope = await api<AchvEnvelope>('/achv/summary')
    state.value = envelope.state
    profile.value = envelope.data
    warning.value = envelope.warning ?? ''
  } catch (reason) {
    if (reason instanceof ApiError && reason.status === 404) {
      state.value = { connected: false, source: null, uid: null, nickname: null, fetched_at: null, stale: false, phone: null }
      profile.value = null
    } else {
      formError.value = message(reason)
    }
  } finally {
    pending.value = false
  }
}

function stopPolling() {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

function openHgLogin() {
  formError.value = ''
  const popup = window.open('/hg/user/login', 'hg-login', 'width=520,height=760')
  if (!popup) {
    formError.value = '浏览器拦截了新窗口，请允许本站弹窗后重试'
    return
  }
  webState.value = 'waiting'
  stopPolling()
  pollTimer = window.setInterval(() => { void checkCapture() }, 1500)
}

async function checkCapture() {
  try {
    const result = await api<{ ready: boolean; access_token?: string; uid?: string }>('/hg/capture')
    if (!result.ready || !result.access_token) return
    stopPolling()
    webState.value = 'syncing'
    const envelope = await api<AchvEnvelope>('/achv/session', post({
      access_token: result.access_token,
      uid: result.uid || undefined,
    }))
    void api('/hg/capture', { method: 'DELETE' }).catch(() => undefined)
    state.value = envelope.state
    profile.value = envelope.data
    warning.value = (envelope.warnings ?? []).join('；')
    webState.value = 'done'
    notify.success('已用鹰角通行证完成绑定')
  } catch (reason) {
    stopPolling()
    webState.value = 'idle'
    formError.value = message(reason)
  }
}

async function connect() {
  formError.value = ''
  busy.value = true
  try {
    const body = mode.value === 'hypergryph'
      ? { phone: phone.value.trim(), password: password.value }
      : { token: token.value.trim() }
    const envelope = await api<AchvEnvelope>('/achv/session', post(body))
    state.value = envelope.state
    profile.value = envelope.data
    warning.value = (envelope.warnings ?? []).join('；')
    password.value = ''
    token.value = ''
    notify.success('已绑定，成就档案已更新')
  } catch (reason) {
    formError.value = message(reason)
  } finally {
    busy.value = false
  }
}

async function refresh() {
  busy.value = true
  try {
    const envelope = await api<AchvEnvelope>('/achv/summary?refresh=true')
    state.value = envelope.state
    profile.value = envelope.data
    warning.value = envelope.warning ?? ''
    notify.success('已刷新')
  } catch (reason) {
    if (reason instanceof ApiError && reason.status === 404) {
      await load()
      notify.warning('绑定已失效，请重新连接')
    } else {
      formError.value = message(reason)
    }
  } finally {
    busy.value = false
  }
}

async function disconnect() {
  busy.value = true
  try {
    await api('/achv/session', { method: 'DELETE' })
    state.value = { connected: false, source: null, uid: null, nickname: null, fetched_at: null, stale: false, phone: null }
    profile.value = null
    warning.value = ''
    notify.success('已解除绑定')
  } catch (reason) {
    formError.value = message(reason)
  } finally {
    busy.value = false
  }
}

onMounted(load)
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="achievements-page">
    <p v-if="pending" class="load-message" role="status">正在读取成就档案…</p>

    <template v-else>
      <p v-if="formError" class="load-message" role="alert">{{ formError }}</p>

      <section v-if="!connected" class="panel connect">
        <header class="connect-head">
          <h2>绑定成就数据源</h2>
          <p class="muted">成就统计来自卫戍协议 H5 的 <code>playerSummary</code> 接口，需要该接口的 <code>code</code> 令牌。</p>
        </header>
        <div class="tabs" role="tablist">
          <button type="button" role="tab" :aria-selected="mode === 'token'" @click="mode = 'token'">拿令牌（推荐）</button>
          <button type="button" role="tab" :aria-selected="mode === 'hypergryph'" @click="mode = 'hypergryph'">账号密码</button>
          <button type="button" role="tab" :aria-selected="mode === 'web'" @click="mode = 'web'">网页登录（实验）</button>
        </div>

        <div v-if="mode === 'web'" class="connect-form">
          <NButton type="primary" size="large" :loading="webState === 'syncing'" @click="openHgLogin">
            {{ webState === 'waiting' ? '等待登录完成…（点此重开窗口）' : '打开鹰角通行证登录页' }}
          </NButton>
          <p class="hint">
            {{ webState === 'waiting'
              ? '在新窗口里登录；登录成功后本页会自动继续。'
              : webState === 'done'
                ? '已登录并完成绑定。'
                : '实验功能：本站反代官方登录页，登录成功后自动取一次 access token。官方页面在这里白屏或登录不了时，请改用「拿令牌」。' }}
          </p>
        </div>

        <form v-if="mode === 'hypergryph'" class="connect-form" @submit.prevent="connect">
          <label class="filter-field">手机号
            <NInput v-model:value="phone" size="large" placeholder="鹰角通行证手机号" :input-props="{ autocomplete: 'username', maxlength: 32 }" />
          </label>
          <label class="filter-field">密码
            <NInput v-model:value="password" type="password" size="large" show-password-on="click"
              placeholder="鹰角通行证密码" :input-props="{ autocomplete: 'current-password', maxlength: 256 }" />
          </label>
          <NButton type="primary" size="large" attr-type="submit" :loading="busy">用通行证连接</NButton>
          <p class="hint">服务端换取 u8 token，密码不入库。鹰角可能对直登做风控，失败请用「拿令牌」。</p>
        </form>

        <form v-if="mode === 'token'" class="connect-form" @submit.prevent="connect">
          <ol class="steps">
            <li>手机/模拟器里打开游戏 → 进入「卫戍协议 · 成就」页面。</li>
            <li>复制这一页的地址栏链接（形如 <code>…/autoChess/index?…&amp;u8_token=…</code>）。</li>
            <li>粘贴到下面，点「用令牌连接」。链接里的 <code>u8_token</code> 就是接口的 <code>code</code>。</li>
          </ol>
          <label class="filter-field">成就页链接或 code
            <NInput v-model:value="token" type="textarea" size="large" :autosize="{ minRows: 3, maxRows: 6 }"
              placeholder="https://ak-webview.hypergryph.com/autoChess/index?…&u8_token=…　或　F8sCSjHpm…" />
          </label>
          <NButton type="primary" size="large" attr-type="submit" :loading="busy">用令牌连接</NButton>
          <p class="hint">
            抓过包的话，<code>playerSummary?code=</code> 后面那一串同样可用。
          </p>
          <aside class="risk-box" role="note">
            <h4>风险提示 · 使用前必读</h4>
            <ul>
              <li><b>账号风险</b>：本页的自动取数属于非官方用法（解析本机客户端登录态换令牌），可能触发风控，最坏导致账号被限制或封禁，后果自负。</li>
              <li><b>隐私</b>：本机助手会读取注册表与游戏本地登录数据，在本地内存解密，不上传第三方；请勿在他人机器运行，也不要外传解出的令牌。</li>
              <li><b>时效</b>：令牌只有小时级寿命，客户端常量随游戏版本变化，随时可能失效。</li>
              <li><b>范围</b>：仅限自己的账号与机器、个人自用；禁止代跑他人账号、批量采集或对外提供服务。</li>
              <li><b>归属</b>：本项目与鹰角网络无关联，游戏内容与商标归其所有。</li>
            </ul>
            <p class="risk-actions">
              本机助手：
              <a href="/download/ArknightsAchvAgent.exe" download>下载 ArknightsAchvAgent.exe</a>
              <span class="muted">（源码见仓库 <code>agent/achv_agent.py</code>，建议自行构建）</span>
            </p>
          </aside>
        </form>
      </section>

      <template v-else-if="profile">
        <section class="panel strip">
          <div class="namecard namecard--player">
            <img v-if="profile.player.name_card" :key="profile.player.name_card" class="namecard-art"
              :src="nameCardLocal(profile.player.name_card)" alt=""
              @error="nameCardFallback($event, profile.player.name_card)" />
            <img class="namecard-avatar" :src="avatarUrl(profile.player.avatar)" alt=""
              @error="avatarFallback($event, profile.player.avatar)" />
            <div class="namecard-copy">
              <h2>{{ profile.player.nickname || '未命名玩家' }}</h2>
              <small v-if="profile.player.nick_number">#{{ profile.player.nick_number }}</small>
            </div>
          </div>
          <dl class="strip-meta">
            <div><dt>UID</dt><dd>{{ profile.player.uid }}</dd></div>
            <div v-if="profile.player.level != null"><dt>博士等级</dt><dd>{{ profile.player.level }}</dd></div>
            <div v-if="profile.season.name || profile.season.version"><dt>赛季</dt><dd>{{ profile.season.name }} {{ profile.season.version }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ fetched }}</dd></div>
          </dl>
          <div class="strip-actions">
            <NButton size="small" secondary :loading="busy" @click="refresh">刷新</NButton>
            <NButton size="small" quaternary :loading="busy" @click="disconnect">解绑</NButton>
          </div>
        </section>

        <p v-if="warning" class="load-message" role="status">{{ warning }}</p>

        <section class="panel block">
          <div class="achv-cols">
            <div class="achv-radar">
              <div class="split"><h3>卫戍成就</h3><span class="period">0–100</span></div>
              <AchievementRadar v-if="profile.dimensions.length" :items="profile.dimensions" />
              <p v-else class="empty-radar muted">暂无六维成就数据</p>
            </div>
            <div class="achv-titles">
              <div class="split"><h3>称号一览</h3><span class="period">{{ overviewTitles.length }} 项</span></div>
              <ul class="title-grid">
                <li v-for="title in overviewTitles" :key="title.id">
                  <img class="title-icon" :src="titleIconUrl(title)" alt="" @error="hideOnError" />
                  <span class="title-name">{{ title.name }}</span>
                  <strong class="title-value">{{ title.value }}</strong>
                </li>
              </ul>
              <div class="split gap"><h3>特殊称号</h3><span class="period">{{ specialTitles.length }} 项</span></div>
              <ul class="title-grid">
                <li v-for="title in specialTitles" :key="title.id">
                  <img class="title-icon" :src="titleIconUrl(title)" alt="" @error="hideOnError" />
                  <span class="title-name">{{ title.name }}</span>
                  <strong class="title-value">{{ title.value }}</strong>
                </li>
              </ul>
            </div>
          </div>
        </section>

        <section class="panel block">
          <div class="split"><h3>社交数据</h3></div>
          <div class="social-grid">
            <div class="social-metrics" :class="{ 'social-metrics--wide': !teammate }">
              <article class="metric-card">
                <img v-if="trophyIcon" :src="trophyIcon" alt="" class="metric-art" />
                <div><span>已获奖杯</span><strong>{{ profile.trophy.total }}</strong></div>
              </article>
              <article class="metric-card">
                <img :src="likeIcon" alt="" class="metric-art metric-art--like" />
                <div><span>已获赞</span><strong>{{ profile.likes }}</strong></div>
              </article>
            </div>
            <article v-if="teammate" class="mate-card">
              <div class="namecard namecard--mate">
                <img v-if="teammate.name_card" :key="teammate.name_card" class="namecard-art"
                  :src="nameCardLocal(teammate.name_card)" alt="" @error="nameCardFallback($event, teammate.name_card)" />
                <img class="namecard-avatar" :src="avatarUrl(teammate.avatar)" alt="" @error="avatarFallback($event, teammate.avatar)" />
                <div class="namecard-copy">
                  <strong>{{ teammate.nickname || '未命名玩家' }}</strong>
                  <small v-if="teammate.nick_number">#{{ teammate.nick_number }}</small>
                </div>
              </div>
              <dl class="mate-stats">
                <div><dt>最常共同游玩</dt><dd>{{ teammate.plays }} <small>场次</small></dd></div>
                <div><dt>最多胜场</dt><dd>{{ teammate.wins }} <small>场次</small></dd></div>
              </dl>
            </article>
          </div>
        </section>

        <section class="panel block">
          <div class="split">
            <h3>已获得特殊策略标识</h3>
            <span class="period">{{ profile.bands.summary.mastered }} / {{ profile.bands.summary.total }}</span>
          </div>
          <ul class="badges">
            <li v-for="badge in badgeList" :key="badge.id" class="badge" :data-master="badge.obtained">
              <div class="badge-visual">
                <img class="badge-art" :src="badgeUrl(badge)" alt="" @error="badgeFallback($event, badge)" />
                <span class="badge-mark">
                  <img :src="markUrl(badge)" :alt="badge.obtained ? '已精通' : '未精通'" />
                </span>
              </div>
              <strong>{{ badge.name }}</strong>
            </li>
          </ul>
          <div class="split gap"><h3>常用分队</h3><span class="period">TOP3</span></div>
          <div class="band-cards">
            <article v-for="(band, index) in profile.bands.top" :key="band.id" class="band-card"
              :data-rank="index + 1" :title="band.effect ?? undefined">
              <span class="band-rank">TOP{{ index + 1 }}</span>
              <div class="band-medal">
                <img class="band-art" :src="'/art/strategy-' + band.id + '.png'" :alt="band.name ?? ''"
                  @error="bandFallback($event, band)" />
              </div>
              <strong class="band-name">{{ band.name }}</strong>
              <div class="band-stats">
                <div class="band-stat">
                  <b>{{ band.winning_rate != null ? band.winning_rate + '%' : '—' }}</b>
                  <span>胜率</span>
                </div>
                <div class="band-stat"><b>×{{ band.value }}</b><span>场次</span></div>
              </div>
              <span class="band-meter" :style="{ '--rate': (band.winning_rate ?? 0) + '%' }" aria-hidden="true"></span>
            </article>
          </div>
        </section>
      </template>

      <div v-else class="loading-shell" role="status"><NSpin size="small" /> 正在同步…</div>
    </template>
  </div>
</template>

<style scoped>
.achievements-page { display: grid; gap: 1rem; min-width: 0; }
.achievements-page > .load-message { margin: 0; }
.connect { padding: 1.5rem; display: grid; gap: 1rem; }
.connect-head h2 { margin-bottom: .4rem; }
.connect-head code, .hint code, .steps code { background: var(--inset); border: 1px solid var(--line); border-radius: 4px; padding: 0 .25rem; }
.tabs { display: flex; gap: .5rem; flex-wrap: wrap; }
.tabs button {
  padding: .45rem .9rem; border-radius: 999px; border: 1px solid var(--control-line);
  background: var(--inset); color: var(--muted); cursor: pointer; font: inherit;
}
.tabs button[aria-selected='true'] { border-color: var(--accent); color: var(--accent); }
.connect-form { display: grid; gap: .9rem; max-width: 36rem; }
.hint { color: var(--muted); font-size: .8125rem; line-height: 1.6; }
.steps { margin: 0; padding-left: 1.25rem; display: grid; gap: .35rem; color: var(--muted); font-size: .8125rem; line-height: 1.7; }
.row-actions { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; }
.risk-box {
  border: 1px solid rgba(232, 161, 60, .45); border-radius: 6px;
  background: rgba(232, 161, 60, .08); padding: .8rem .9rem; display: grid; gap: .45rem;
}
.risk-box h4 { color: #e8a13c; font-size: .8125rem; letter-spacing: .04em; }
.risk-box ul { margin: 0; padding-left: 1.1rem; display: grid; gap: .3rem; color: var(--muted); font-size: .78rem; line-height: 1.6; }
.risk-box b { color: var(--text); font-weight: 600; }
.risk-actions { margin: .2rem 0 0; font-size: .8125rem; display: flex; flex-wrap: wrap; gap: .45rem; align-items: baseline; }
.risk-actions a { color: var(--accent); text-decoration: underline; }
.risk-actions code { background: var(--inset); border: 1px solid var(--line); border-radius: 4px; padding: 0 .25rem; }

.achv-cols { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); gap: clamp(1rem, 3vw, 2rem); }
.achv-radar { display: grid; grid-template-rows: auto 1fr; min-width: 0; }
.empty-radar { display: grid; min-height: 10rem; place-items: center; }

.strip {
  display: grid; grid-template-columns: minmax(16rem, 20rem) minmax(0, 1fr) auto;
  align-items: center; gap: .9rem clamp(1rem, 2.5vw, 2rem);
  padding: .85rem clamp(.8rem, 2.5vw, 1.5rem);
}
.namecard {
  position: relative; isolation: isolate; overflow: hidden; display: flex; align-items: center; gap: .65rem;
  width: 100%; min-width: 0; min-height: 3.75rem; aspect-ratio: 20 / 7;
  padding: .45rem .65rem; border-radius: 6px; background: var(--inset);
}
.namecard-art { position: absolute; z-index: -2; inset: 0; width: 100%; height: 100%; object-fit: contain; }
.namecard:has(.namecard-art:not([hidden])) {
  background: transparent; color: #f1f5fa; padding-bottom: calc(.45rem + 5.5%);
}
.namecard:has(.namecard-art:not([hidden]))::before {
  content: ''; position: absolute; z-index: -1; inset: 0 2.8% 16.5%; border-radius: 6px;
  background: linear-gradient(90deg, #0c1219b8, #0c121970 53%, transparent 90%);
}
.namecard:has(.namecard-art:not([hidden])) small { color: #d1d9e4; }
.namecard-avatar { flex: none; width: 2.5rem; aspect-ratio: 1; border-radius: 4px; border: 1px solid var(--line); object-fit: cover; }
.namecard-copy { display: grid; min-width: 0; line-height: 1.25; overflow-wrap: anywhere; }
.namecard-copy h2 { font-size: clamp(1rem, 1.6vw, 1.2rem); }
.namecard-copy strong { font-size: .875rem; }
.namecard-copy small { font-size: .75rem; }
.namecard--player { max-width: 20rem; }
.namecard--player .namecard-avatar { width: clamp(2.6rem, 5vw, 3.2rem); }
.strip-meta { display: flex; flex-wrap: wrap; gap: .55rem clamp(.9rem, 2.4vw, 1.75rem); }
.strip-meta dt { color: var(--muted); font-size: .75rem; }
.strip-meta dd { font-size: .875rem; font-variant-numeric: tabular-nums; }
.strip-actions { display: flex; gap: .4rem; }

.block { padding: 1.15rem clamp(.8rem, 2.5vw, 1.5rem); }
.block h3 { position: relative; padding-left: .7rem; font-size: 1.05rem; letter-spacing: .02em; }
.block h3::before {
  content: ''; position: absolute; left: 0; top: .18em; bottom: .18em; width: 3px;
  background: linear-gradient(180deg, var(--accent), color-mix(in srgb, var(--accent) 25%, transparent));
  border-radius: 2px;
}
.split { align-items: baseline; gap: 1rem; border-bottom: 1px solid var(--line); padding-bottom: .55rem; }
.split.gap { margin-top: 1.25rem; }
.period { white-space: nowrap; letter-spacing: .04em; }

.title-grid {
  list-style: none; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: clamp(.7rem, 2vw, 1.4rem); margin: .45rem 0 0; padding: 0;
}
.title-grid li { display: flex; align-items: center; gap: .5rem; padding: .38rem 0; border-bottom: 1px solid var(--line); }
.title-icon { flex: none; width: 1.25rem; height: 1.25rem; object-fit: contain; }
.title-name { flex: 1; min-width: 0; overflow-wrap: anywhere; font-size: .875rem; line-height: 1.35; }
.title-value { font-family: var(--numbers); font-size: 1.18rem; color: var(--accent); font-variant-numeric: tabular-nums; }

.social-grid {
  display: grid; grid-template-columns: minmax(14rem, 1fr) minmax(0, 2fr); align-items: center;
  gap: .85rem clamp(1rem, 2vw, 1.5rem); margin-top: .85rem;
}
.social-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .65rem; }
.social-metrics--wide { grid-column: 1 / -1; max-width: 28rem; }
.metric-card {
  display: flex; align-items: center; gap: clamp(.45rem, 1vw, .8rem); min-height: 4.5rem;
  padding: .65rem clamp(.55rem, 1vw, .9rem); background: var(--inset); border: 1px solid var(--line); border-radius: 6px;
}
.metric-card span, .mate-stats dt { display: block; color: var(--muted); font-size: .8125rem; }
.metric-card strong, .mate-stats dd {
  font-family: var(--numbers); font-variant-numeric: tabular-nums;
  font-size: clamp(1.35rem, 2.5vw, 1.85rem); font-weight: 700; line-height: 1.12; color: var(--accent);
}
.metric-art { flex: none; width: clamp(1.85rem, 5vw, 3rem); aspect-ratio: 1; object-fit: contain; }
.metric-art--like { padding: min(.3rem, 1.1vw); }
.mate-card {
  display: grid; grid-template-columns: minmax(0, 17.5rem) minmax(0, 1fr); align-items: center;
  gap: .8rem clamp(.8rem, 2.2vw, 1.5rem); border-inline-start: 1px solid var(--line);
  padding-inline-start: clamp(1rem, 2vw, 1.5rem);
}
.namecard--mate { max-width: 17.5rem; }
.mate-stats { display: grid; grid-template-columns: repeat(2, minmax(0, 8rem)); gap: .75rem; }
.mate-stats dd { margin-top: .2rem; }
.mate-stats small { font-size: .72rem; font-weight: 500; white-space: nowrap; }

.badges {
  list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 7.2rem), 1fr));
  gap: .75rem; padding: 0; margin: .85rem 0 0;
}
.badge {
  display: grid; grid-template-rows: auto 1fr; gap: .42rem; justify-items: center; min-width: 0;
  padding: .45rem .45rem .55rem; border: 1px solid var(--line); border-radius: 6px; background: var(--inset);
}
.badge-visual { position: relative; width: 100%; max-width: 8rem; aspect-ratio: 1; }
.badge-art { display: block; width: 100%; height: 100%; object-fit: contain; }
.badge strong { align-self: center; font-size: .875rem; line-height: 1.3; text-align: center; overflow-wrap: anywhere; }
.badge-mark {
  position: absolute; top: .2rem; right: .2rem; display: grid; place-items: center;
  width: 1.65rem; aspect-ratio: 1; border-radius: 4px;
  border: 1px solid #8ae6d1; background: #102825;
}
.badge-mark img { display: block; width: 100%; height: 100%; object-fit: contain; transform: scale(1.25); }
.badge[data-master='false'] .badge-mark { border-color: #edaa58; background: #322313; }

.band-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 15.5rem), 1fr)); gap: .9rem; margin-top: 1rem; }
.band-card {
  position: relative; display: grid; align-items: center;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-areas: "medal name" "medal stats";
  column-gap: 1rem; row-gap: .45rem;
  min-height: 6.4rem; padding: 1rem 1.15rem 1.05rem 1rem; border-radius: 8px; overflow: hidden;
  background: radial-gradient(75% 120% at 10% 42%, color-mix(in srgb, var(--win) 14%, transparent), transparent 62%), var(--inset);
  border: 1px solid var(--line);
  transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease;
}
.band-card::before, .band-card::after {
  content: ''; position: absolute; width: 13px; height: 13px; pointer-events: none;
  border: 1px solid rgba(127, 240, 210, .38);
}
.band-card::before { top: 5px; left: 5px; border-right: 0; border-bottom: 0; }
.band-card::after { right: 5px; bottom: 5px; border-left: 0; border-top: 0; }
.band-card:hover {
  border-color: rgba(94, 220, 190, .46); transform: translateY(-2px);
  box-shadow: 0 10px 26px -16px rgba(0, 0, 0, .9);
}
.band-card[data-rank='1'] { border-color: rgba(127, 240, 210, .34); }
.band-card[data-rank='1'] .band-medal::before { box-shadow: inset 0 0 0 1px rgba(127, 240, 210, .32); }
.band-rank {
  position: absolute; top: .5rem; right: .55rem; z-index: 1;
  padding: .1rem .4rem; border-radius: 3px;
  font-family: var(--numbers); font-size: .6875rem; letter-spacing: .12em; color: var(--accent);
  background: rgba(94, 168, 152, .14); border: 1px solid rgba(94, 168, 152, .22);
}
.band-medal { grid-area: medal; position: relative; display: grid; place-items: center; width: 5.1rem; height: 5.1rem; }
.band-medal::before {
  content: ''; position: absolute; inset: 3%; border-radius: 50%;
  background: radial-gradient(circle at 50% 45%, rgba(127, 240, 210, .18), rgba(127, 240, 210, 0) 68%);
  box-shadow: inset 0 0 0 1px rgba(127, 240, 210, .16);
}
/* 分队图是 180×180 的方形海报，用径向遮罩裁成圆形头像，边缘自然融进卡片底色 */
.band-art {
  position: relative; width: 4.7rem; height: 4.7rem; object-fit: cover;
  -webkit-mask-image: radial-gradient(circle at 50% 48%, #000 50%, rgba(0, 0, 0, .6) 66%, transparent 80%);
  mask-image: radial-gradient(circle at 50% 48%, #000 50%, rgba(0, 0, 0, .6) 66%, transparent 80%);
  filter: saturate(1.05) contrast(1.04) drop-shadow(0 0 9px rgba(94, 220, 190, .3));
}
.band-name {
  grid-area: name; justify-self: start; align-self: end; padding-right: 2.2rem;
  text-align: left; font-size: 1rem; font-weight: 600; line-height: 1.2; overflow-wrap: anywhere;
}
.band-stats { grid-area: stats; justify-self: start; align-self: start; display: flex; align-items: flex-start; gap: .8rem; font-family: var(--numbers); }
.band-stat { display: grid; justify-items: start; gap: .15rem; }
.band-stat b { font-size: 1rem; font-weight: 600; line-height: 1; color: var(--accent); }
.band-stat span { font-size: .6875rem; letter-spacing: .06em; color: var(--muted); }
.band-stats > .band-stat + .band-stat { border-left: 1px solid rgba(94, 168, 152, .22); padding-left: .8rem; }
.band-meter { position: absolute; left: 0; right: 0; bottom: 0; height: 2px; background: rgba(94, 168, 152, .16); }
.band-meter::after {
  content: ''; position: absolute; inset: 0 auto 0 0; width: var(--rate, 0%);
  background: linear-gradient(90deg, rgba(127, 240, 210, .32), #7ff0d2);
  box-shadow: 0 0 8px rgba(127, 240, 210, .4);
}
.loading-shell { display: flex; gap: .6rem; align-items: center; }

@media (max-width: 920px) {
  .strip { grid-template-columns: minmax(14rem, 17rem) minmax(0, 1fr); }
  .namecard--player { grid-row: span 2; }
  .strip-actions { justify-self: start; }
  .social-grid { grid-template-columns: minmax(0, 1fr); }
  .mate-card { padding: .85rem 0 0; border-inline-start: 0; border-top: 1px solid var(--line); }
}
@media (max-width: 820px) {
  .achv-cols { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 560px) {
  .strip { grid-template-columns: minmax(0, 1fr); }
  .namecard--player { grid-row: auto; }
  .strip-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .mate-card { grid-template-columns: minmax(0, 1fr); }
  .badges { grid-template-columns: repeat(auto-fill, minmax(min(100%, 5.4rem), 1fr)); gap: .55rem; }
}
</style>

