import type { Peak, Result } from './models'

const numberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 })
const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const shortFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const clockFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})

export const number = (value: number | null) => value === null ? '—' : numberFormatter.format(value)
/** 增减量：正数补「+」号，便于和总量区分。 */
export const signed = (value: number | null) => value === null ? '—' : (value > 0 ? '+' : '') + numberFormatter.format(value)
export const percent =(value: number) => (value * 100).toFixed(1) + '%'
export const dateTime = (value: string) => dateFormatter.format(new Date(value))
export const shortTime = (value: string) => shortFormatter.format(new Date(value)).replace(/\//g, '-')
export const clockTime = (value: string) => clockFormatter.format(new Date(value))
export const resultLabel = (value: Result) => value === 'win' ? '胜' : '负'
export const peakText = (value: Peak | null) => value ? value.names.join('、') + ' ' + number(value.layers) + ' 层' : '—'
export const protocolLabel = (value: string) => value === 'V3_1' ? '规程协议 1' : value
export const difficultyLabel = (value: string) => value.replace(/^规程等级\s*(\d+)$/, '规程等级 $1')

const PLAY_ORDER = ['独立模拟', '联合模拟']
const TIER_ORDER = ['标准模拟', '险境模拟', '绝境模拟', '终极模拟']

/** 模拟方式：独立模拟在前，联合模拟在后。 */
export const playRank = (value: string) => {
  const index = PLAY_ORDER.indexOf(value)
  return index < 0 ? PLAY_ORDER.length : index
}

/** 难度：独立模拟按规程等级数字升序（极速模拟最前），联合模拟按 标准 < 险境 < 绝境 < 终极。 */
export function difficultyRank(value: string): [number, number] {
  const tier = TIER_ORDER.indexOf(value)
  if (tier >= 0) return [1, tier]
  if (value === '极速模拟') return [0, -1]
  const level = value.match(/^规程等级\s*(\d+)$/)
  if (level) return [0, Number(level[1])]
  return [2, 0]
}

export const compareDifficulty = (a: string, b: string) => {
  const [groupA, rankA] = difficultyRank(a)
  const [groupB, rankB] = difficultyRank(b)
  return groupA - groupB || rankA - rankB || a.localeCompare(b, 'zh-Hans-CN')
}

const MAJOR_BONDS = [
  '炎', '乌萨斯', '维多利亚', '伊比利亚', '阿戈尔', '莱塔尼亚', '卡西米尔',
  '萨尔贡', '叙拉古', '谢拉格', '哥伦比亚', '玻利瓦尔', '雷姆必拓', '米诺斯',
]

/** 并列时优先展示大盟约（如「炎」），没有命中则取第一个。 */
export function pickMajorBond(names: string[]): string {
  return MAJOR_BONDS.find(name => names.includes(name)) ?? names[0] ?? ''
}

/** 并列时按字典序（汉字按拼音）取最靠前的一个，用于只展示一个名字的地方。 */
export function firstBond(names: string[]): string {
  return [...names].sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))[0] ?? ''
}
