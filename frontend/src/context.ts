import { inject, type InjectionKey, type Ref } from 'vue'
import type { Facet, Filters, Role } from './models'

export const newFilters = (): Filters => ({
  protocol: '', play: '', difficulty: '', start: '', end: '', include_exits: false,
})

/** 三个页面共享的登录态、当前角色、筛选条件和数据版本。 */
export interface LogbookContext {
  role: Ref<Role | null>
  roles: Ref<Role[]>
  filters: Filters
  facets: Ref<Facet[]>
  revision: Ref<number>
  createRole: (name: string) => Promise<void>
  renameRole: (id: string, name: string) => Promise<void>
  deleteRole: (id: string) => Promise<void>
  selectRole: (id: string) => void
  refresh: () => void
}

export const logbookKey: InjectionKey<LogbookContext> = Symbol('logbook')

export function logbook(): LogbookContext {
  const context = inject(logbookKey)
  if (!context) throw new Error('Missing logbook context')
  return context
}
