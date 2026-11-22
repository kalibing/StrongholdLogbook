import type { Peak, Result } from './models'

const numberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 })
const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})

export const number = (value: number | null) => value === null ? '—' : numberFormatter.format(value)
export const percent = (value: number) => (value * 100).toFixed(1) + '%'
export const dateTime = (value: string) => dateFormatter.format(new Date(value))
export const resultLabel = (value: Result) => value === 'win' ? '胜' : '负'
export const peakText = (value: Peak | null) => value ? value.names.join('、') + ' ' + number(value.layers) + ' 层' : '—'
export const protocolLabel = (value: string) => value === 'V3_1' ? '规程协议 1' : value
