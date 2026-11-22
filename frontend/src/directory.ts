import { api } from './api'
import { portrait } from './icons'

interface Entry { id: string; name: string }

let cache: Promise<Map<string, string>> | null = null

/** 名称 → 干员 ID，用于给「发起者」这类纯文本字段补头像。 */
export function loadDirectory(): Promise<Map<string, string>> {
  cache ??= api<{ operators: Entry[] }>('/directory')
    .then(data => new Map(data.operators.map(item => [item.name, item.id])))
    .catch(() => new Map<string, string>())
  return cache
}

export function avatarFor(names: Map<string, string>, value: string | null): string | null {
  if (!value) return null
  const id = names.get(value)
  return id ? portrait(id) : null
}
