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

export const number = (value: number | null) => value === null ? '—' : numberFormatter.format(value)
export const percent = (value: number) => (value * 100).toFixed(1) + '%'
export const dateTime = (value: string) => dateFormatter.format(new Date(value))
export const shortTime = (value: string) => shortFormatter.format(new Date(value)).replace(/\//g, '-')
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
