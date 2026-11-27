<script setup lang="ts">
import { DIFFICULTY_ICONS, MODE_ICONS } from '../assets'
import TierTag from '../components/TierTag.vue'

const tiers = [
  { label: '极速模拟', file: 'tier-fast.png', asset: 'mode_fast_icon', note: '塔 + 闪电' },
  { label: '标准模拟', file: 'tier-standard-rook.png', asset: 'mode_funny_icon', note: '素塔（对照游戏选关界面）' },
  { label: '险境模拟', file: 'tier-normal.png', asset: 'mode_normal_icon', note: '塔 + 交叉剑' },
  { label: '绝境模拟', file: 'tier-hard.png', asset: 'mode_hard_icon', note: '城垛 + 交叉剑' },
  { label: '终极模拟', file: 'tier-abyss.png', asset: 'mode_abyss_icon', note: '城垛 + 交叉剑 + 警告' },
]

const raws = Object.entries(MODE_ICONS)

// 图标挂在「难度 / 等级」列；规程等级按 difficultyIcon 的四档取图。
const samples = [
  { time: '11-20 21:14', win: true, play: '独立模拟', difficulty: '极速模拟' },
  { time: '11-20 20:52', win: false, play: '独立模拟', difficulty: '规程等级 3' },
  { time: '11-19 23:07', win: true, play: '独立模拟', difficulty: '规程等级 7' },
  { time: '11-19 22:31', win: true, play: '独立模拟', difficulty: '规程等级 12' },
  { time: '11-19 21:05', win: true, play: '独立模拟', difficulty: '规程等级 18' },
  { time: '11-18 19:40', win: false, play: '联合模拟', difficulty: '标准模拟' },
  { time: '11-18 18:22', win: true, play: '联合模拟', difficulty: '终极模拟' },
]

/** 规程等级四档：依据见 assets.ts 的 difficultyIcon 注释。 */
const levelBands = [
  { range: '规程等级 1–4', tier: '标准模拟', basis: 'PRTS 关键目标：【标准模拟】或【规程等级1~4】' },
  { range: '规程等级 5–8', tier: '险境模拟', basis: 'PRTS 关键目标：【险境模拟】或【规程等级5~8】' },
  { range: '规程等级 9–14', tier: '绝境模拟', basis: '解锁规程等级 9 时开放险境，往上一档（推断）' },
  { range: '规程等级 15–20', tier: '终极模拟', basis: '解锁规程等级 15 时开放绝境，往上一档（推断）' },
]
</script>

<template>
  <section class="panel table-panel">
    <div class="split table-heading">
      <h2>难度图标</h2>
      <span class="period">ui/autochess/[uc]autochesscommon.ab</span>
    </div>
    <div class="icon-gallery">
      <p class="muted">
        从本机 PC 端 AB 包原生拆出的 sprite（<code>mode_*_icon</code>），按层级上色后放在
        <code>/art/tier-*.png</code>；白色原图在 <code>/art/mode-*.png</code>。
      </p>
      <div class="icon-row">
        <figure v-for="tier in tiers" :key="tier.label">
          <img :src="'/art/' + tier.file" width="48" height="48" :alt="tier.label">
          <figcaption>{{ tier.label }}</figcaption>
        </figure>
      </div>
    </div>
  </section>

  <section class="panel table-panel">
    <div class="split table-heading">
      <h2>多尺寸 / 白色原图</h2>
      <span class="period">18 · 24 · 32 px</span>
    </div>
    <div class="icon-gallery">
      <div class="icon-row">
        <div v-for="tier in tiers" :key="tier.label" class="icon-sizes">
          <img :src="'/art/' + tier.file" width="18" height="18" :alt="tier.label">
          <img :src="'/art/' + tier.file" width="24" height="24" :alt="tier.label">
          <img :src="'/art/' + tier.file" width="32" height="32" :alt="tier.label">
        </div>
      </div>
      <div class="icon-row">
        <figure v-for="[label, src] in raws" :key="label">
          <img class="icon-original" :src="src" width="56" height="56" :alt="label">
          <figcaption>{{ label }}<br><code>{{ src }}</code></figcaption>
        </figure>
      </div>
    </div>
  </section>

  <section class="panel table-panel">
    <div class="split table-heading">
      <h2>对局记录里的样子</h2>
      <span class="period">TierTag · 18px</span>
    </div>
    <div class="scroll">
      <table class="history-table">
        <thead>
          <tr><th scope="col">开局时间</th><th scope="col">战果</th><th scope="col">模拟方式</th><th scope="col">难度 / 等级</th></tr>
        </thead>
        <tbody>
          <tr v-for="sample in samples" :key="sample.time">
            <td>{{ sample.time }}</td>
            <td><span class="chip" :class="{ loss: !sample.win }">{{ sample.win ? '胜' : '负' }}</span></td>
            <td data-label="模拟方式">{{ sample.play }}</td>
            <td data-label="难度 / 等级"><TierTag :label="sample.difficulty" /></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel table-panel">
    <div class="split table-heading">
      <h2>规程等级分档</h2>
      <span class="period">独立模拟复用联合模拟的四档图标</span>
    </div>
    <div class="scroll">
      <table class="history-table">
        <thead>
          <tr><th scope="col">等级</th><th scope="col">图标</th><th scope="col">依据</th></tr>
        </thead>
        <tbody>
          <tr v-for="band in levelBands" :key="band.range">
            <td>{{ band.range }}</td>
            <td><TierTag :label="band.tier" /></td>
            <td class="muted">{{ band.basis }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel table-panel">
    <div class="split table-heading">
      <h2>特殊策略标识</h2>
      <span class="period">成就页卡片右上角</span>
    </div>
    <div class="icon-gallery">
      <p class="muted">
        成就页卡片右上角那枚角标 = 卫戍协议 H5 的 <code>mark_pro.fda48b.png</code>（青绿虹彩，63×64）；
        未精通态游戏里是暖橙，用同一张图压色相得到。
        文件：<code>/art/achv-mark-pro.png</code> · <code>/art/achv-mark-pro-orange.png</code>
      </p>
      <div class="icon-row">
        <figure>
          <img src="/art/achv-mark-pro.png" width="63" height="64" alt="精通标识">
          <figcaption>精通（master）</figcaption>
        </figure>
        <figure>
          <img src="/art/achv-mark-pro-orange.png" width="63" height="64" alt="未精通标识">
          <figcaption>未精通（base）</figcaption>
        </figure>
        <figure>
          <img src="/art/achv-mark-pro.png" width="28" height="28" alt="">
          <figcaption>卡片角标 1.25rem</figcaption>
        </figure>
        <figure>
          <img src="/art/achv-mark-pro-orange.png" width="28" height="28" alt="">
          <figcaption>卡片角标（橙）</figcaption>
        </figure>
      </div>
    </div>
  </section>

  <section class="panel table-panel">
    <div class="split table-heading">
      <h2>隐藏首领标记</h2>
      <span class="period">ui/autochess · icon_boss_sp</span>
    </div>
    <div class="icon-gallery">
      <p class="muted">
        原包里是两套素材，不是一张图染两种色：<code>boss_sp_icon</code>（364×260，青主体 + 橙黄点缀）、
        <code>icon_boss_sp_white</code>（274×215，白色剪影）、<code>icon_boss_sp_tiny</code>（80×76，战斗内小号）。
        橙色态 = 白色剪影上色，形状与青色版完全一致。
      </p>
      <div class="icon-row">
        <figure>
          <img src="/art/hidden-boss-mark.png" width="132" height="99" alt="隐藏首领标记（青）">
          <figcaption>彩色（青）</figcaption>
        </figure>
        <figure>
          <img src="/art/hidden-boss-mark-orange.png" width="132" height="103" alt="隐藏首领标记（橙）">
          <figcaption>橙色态</figcaption>
        </figure>
        <figure>
          <img class="icon-on-dark" src="/art/hidden-boss-mark-white.png" width="132" height="103" alt="白色剪影">
          <figcaption>白色剪影</figcaption>
        </figure>
        <figure>
          <img src="/art/hidden-boss-mark-tiny.png" width="67" height="59" alt="小号">
          <figcaption>tiny 67×59</figcaption>
        </figure>
        <figure>
          <span class="dist-total">总 6 场<span class="dist-hidden"><img src="/art/hidden-boss-mark.png" alt="">隐藏 1</span></span>
          <figcaption>行内效果（13px）</figcaption>
        </figure>
      </div>
    </div>
  </section>

  <section class="panel table-panel">
    <div class="split table-heading">
      <h2>对照表</h2>
      <span class="period">{{ tiers.length }} 项</span>
    </div>
    <div class="scroll">
      <table class="history-table">
        <thead>
          <tr><th scope="col">标签</th><th scope="col">文件</th><th scope="col">原始资源</th><th scope="col">形状</th></tr>
        </thead>
        <tbody>
          <tr v-for="tier in tiers" :key="tier.label">
            <td><span class="tier-tag"><img :src="DIFFICULTY_ICONS[tier.label]" width="18" height="18" alt=""><span>{{ tier.label }}</span></span></td>
            <td><code>/art/{{ tier.file }}</code></td>
            <td><code>{{ tier.asset }}</code></td>
            <td>{{ tier.note }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
/* 白色剪影在浅色背景上会消失，垫一块深色底。 */
.icon-on-dark { box-sizing: content-box; padding: 6px; border-radius: 4px; background: #1a2620; }
</style>
