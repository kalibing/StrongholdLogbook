import { STRATEGY_ICONS } from './assets'

/**
 * 卫戍协议里每支「分队」对应一个 band id，也对应一条「策略」。
 * 名称取自规程 V3_1 游戏数据的 bandDataDict 和 bandDataListDict。
 */
export interface Band {
  id: string
  /** 分队名（通常就是发起干员，例如「森蚺」） */
  unit?: string
  /** 策略名（例如「暴躁铁皮」） */
  strategy: string
}

const BANDS: Record<string, { unit: string; strategy: string }> = {
  band_amedic: { unit: 'Touch', strategy: '外勤医疗' },
  band_amiya: { unit: '阿米娅', strategy: '众志合一' },
  band_bond: { unit: '贾维', strategy: '团伙行动' },
  band_bonus: { unit: '复奏', strategy: '二重奏' },
  band_breakaway: { unit: 'Misery', strategy: '消解空间' },
  band_cannot: { unit: '坎诺特', strategy: '利滚利' },
  band_clementia: { unit: '克莱门莎', strategy: '崇高牺牲' },
  band_closeout: { unit: '拜松', strategy: '打包速递' },
  band_copy: { unit: '夕', strategy: '幻画为真' },
  band_damaztic: { unit: '“变形者集群”', strategy: '变形同构' },
  band_dance: { unit: '妮芙', strategy: '溃心领域' },
  band_ducklord: { unit: '鸭爵', strategy: '“神秘顾客”' },
  band_egir: { unit: '歌蕾蒂娅', strategy: '猎人战法' },
  band_emperor: { unit: '大帝', strategy: '加急调派' },
  band_equipment: { unit: 'Mechanist', strategy: '精巧设计' },
  band_evolve: { unit: '大嘴莫布', strategy: '全场聚焦' },
  band_fang: { unit: '芬', strategy: '协力共进' },
  band_fund: { unit: '小贾斯汀', strategy: '私募基金' },
  band_gain: { unit: '铃兰', strategy: '御守之力' },
  band_harold: { unit: '哈洛德', strategy: '人才盲盒' },
  band_high: { unit: '渡桥', strategy: '专享情报' },
  band_iberia: { unit: '引星棘刺', strategy: '出航时刻' },
  band_ioleta: { unit: '伊奥莱塔·罗素', strategy: '统御号令' },
  band_jenga: { unit: '但书', strategy: '条文修正' },
  band_jesica: { unit: '杰西卡', strategy: '集结指示' },
  band_kazimier: { unit: '焰尾', strategy: '骑士团长' },
  band_kjerag: { unit: '休露丝', strategy: '雪域礼赠' },
  band_kjerag2: { unit: '耶拉', strategy: '不融信念' },
  band_lethania: { unit: '车尔尼', strategy: '流动乐章' },
  band_limit: { unit: '坚雷', strategy: '正直教官' },
  band_lmlee: { unit: '老鲤', strategy: '得闲饮茶' },
  band_mech: { unit: '森蚺', strategy: '暴躁铁皮' },
  band_mess: { unit: '昆图斯', strategy: '不稳定要素' },
  band_mlynar: { unit: '玛恩纳', strategy: '业务指标' },
  band_pepe: { unit: '佩佩', strategy: '博学多通' },
  band_pith: { unit: 'Pith', strategy: '优等生' },
  band_prepfin: { unit: '苏苏洛', strategy: '强制休整' },
  band_price: { unit: '天空盒', strategy: '内部货源' },
  band_protect: { unit: '信仰搅拌机', strategy: '献身护卫' },
  band_pudd: { unit: '布丁', strategy: '电气化！' },
  band_qalaisa: { unit: '卡莱莎', strategy: '食腐之蝶' },
  band_random: { unit: '“追随者们”', strategy: '好多委托！' },
  band_rich: { unit: '琳琅诗怀雅', strategy: '最佳品味' },
  band_sargon: { unit: '娜仁图亚', strategy: '沙洲梦魇' },
  band_sarkazb: { unit: '歌利亚', strategy: '坚不可摧' },
  band_sell: { unit: '三船光平', strategy: '东之极道' },
  band_shield: { unit: '桑葚', strategy: '药枚实验' },
  band_siracusa: { unit: '裁度', strategy: '量体裁衣' },
  band_smith: { unit: '奥达', strategy: '全力熔铸' },
  band_substitute: { unit: '巫恋', strategy: '替身娃娃' },
  band_support: { unit: '雅拉', strategy: '人才锁定' },
  band_survive: { unit: '百炼嘉维尔', strategy: '意志鼓舞' },
  band_takecare: { unit: '华法琳', strategy: '重点监护' },
  band_transfer: { unit: '风丸', strategy: '纸片替身' },
  band_treasure: { unit: '寻宝人', strategy: '宝藏探机' },
  band_upgrade: { unit: '缪尔赛思', strategy: '至纯凝结' },
  band_ursus: { unit: '怒潮凛冬', strategy: '无惧风雪' },
  band_victoria: { unit: '洛洛', strategy: '自发制造' },
  band_weakness: { unit: '陈', strategy: '以己之长' },
  band_yan: { unit: '杜遥夜', strategy: '广交豪杰' },
  band_yan2: { unit: '望', strategy: '黑白相易' },
}

const byStrategy = new Map<string, Band>()
const byUnit = new Map<string, Band>()
for (const [id, band] of Object.entries(BANDS)) {
  const entry = { id, ...band }
  byStrategy.set(band.strategy, entry)
  if (band.unit) byUnit.set(band.unit, entry)
}

/** 战绩里存的可能是 band id、分队名或策略名，统一解析成同一条记录。 */
export function resolveBand(value: string | null | undefined): Band | null {
  if (!value) return null
  const text = value.trim()
  if (!text) return null
  if (text.startsWith('band_')) {
    const band = BANDS[text]
    return band ? { id: text, ...band } : null
  }
  return byStrategy.get(text) ?? byUnit.get(text) ?? null
}

export function strategyOf(value: string | null | undefined): string {
  return resolveBand(value)?.strategy ?? value?.trim() ?? ''
}

/**
 * 只用本地图标：官方资源站拒绝跨站引用，生产环境的 CSP 也只放行同源图片。
 * 每个 band 都在 public/art/strategy-<band id>.png 有一张（取自资源站 auto_chess/band_icon），
 * STRATEGY_ICONS 里没登记的按 id 推出路径。
 */
export function strategyIcon(value: string | null | undefined): string | undefined {
  const known = STRATEGY_ICONS[strategyOf(value)]
  if (known) return known
  const id = resolveBand(value)?.id
  return id ? `/art/strategy-${id}.png` : undefined
}

export function unitOf(value: string | null | undefined): string {
  return resolveBand(value)?.unit ?? ''
}

export function bandIcon(value: string | null | undefined): string | null {
  const band = resolveBand(value)
  return band?.unit ?? null
}

export function bandIdOf(value: string | null | undefined): string {
  return resolveBand(value)?.id ?? ''
}
