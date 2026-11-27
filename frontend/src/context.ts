import { inject, type InjectionKey, type Ref } from 'vue'
import type { Facet, Filters, User } from './models'

export const newFilters = (): Filters => ({
  protocol: '', play: '', difficulty: '', start: '', end: '', include_exits: false,
})

export type Theme = 'dark' | 'light'

/** 三个页面共享的登录态、筛选条件、数据版本与主题。 */
export interface LogbookContext {
  filters: Filters
  /** 当前登录账号；改昵称 / 头像后用 setUser 写回，页头和主页同时更新。 */
  user: Ref<User | null>
  setUser: (value: User) => void
  facets: Ref<Facet[]>
  revision: Ref<number>
  theme: Ref<Theme>
  toggleTheme: (event?: Event) => void
  refresh: () => void
}

export const logbookKey: InjectionKey<LogbookContext> = Symbol('logbook')

export function logbook(): LogbookContext {
  const context = inject(logbookKey)
  if (!context) throw new Error('Missing logbook context')
  return context
}
