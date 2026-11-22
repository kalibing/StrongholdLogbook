<script setup lang="ts">
import { DIFFICULTY_ICONS, MODE_ICONS } from '../assets'
import TierTag from '../components/TierTag.vue'

const tiers = [
  { label: '极速模拟', file: 'tier-fast.png', asset: 'mode_fast_icon', note: '塔 + 闪电' },
  { label: '标准模拟', file: 'tier-standard.png', asset: 'mode_fast_icon', note: '旧名，暂用极速图形' },
  { label: '险境模拟', file: 'tier-normal.png', asset: 'mode_normal_icon', note: '塔 + 交叉剑' },
  { label: '绝境模拟', file: 'tier-hard.png', asset: 'mode_hard_icon', note: '城垛 + 交叉剑' },
  { label: '终极模拟', file: 'tier-abyss.png', asset: 'mode_abyss_icon', note: '城垛 + 交叉剑 + 警告' },
]

const raws = Object.entries(MODE_ICONS)

const samples = [
  { time: '11-20 21:14', win: true, play: '极速模拟', difficulty: '规程等级 4' },
  { time: '11-20 20:52', win: false, play: '险境模拟', difficulty: '规程等级 9' },
  { time: '11-19 23:07', win: true, play: '绝境模拟', difficulty: '规程等级 12' },
  { time: '11-19 22:31', win: true, play: '终极模拟', difficulty: '规程等级 13' },
  { time: '11-18 19:40', win: false, play: '联合模拟', difficulty: '规程等级 7' },
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
            <td data-label="模拟方式"><TierTag :label="sample.play" /></td>
            <td data-label="难度 / 等级">{{ sample.difficulty }}</td>
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
