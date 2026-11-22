export interface User { username: string }
export interface Role { id: string; name: string }
export interface Facet { protocol: string; play: string; difficulty: string }
export interface Filters {
  protocol: string
  play: string
  difficulty: string
  start: string
  end: string
  include_exits: boolean
}
export type Result = 'win' | 'loss'
export type Scope = 'recent' | 'all' | 'day'
export interface Peak { layers: number; names: string[] }
export interface Point {
  label: string
  result: Result | null
  layers: number
  peak: Peak | null
  coins: number | null
  average_coins?: number | null
  kills: number | null
  rounds: number | null
}
export interface Operator {
  id: string
  name: string
  count: number
  wins: number
  losses: number
  usage_rate: number
  win_rate: number
}
export interface Overview {
  matches: number
  wins: number
  excluded: number
  start: string | null
  end: string | null
  recent_results: Result[]
  max_layers: number | null
  peak: Peak | null
  total_coins: number | null
  average_coins: number | null
  with_squad: number
  operators: Operator[]
  bonds: { name: string; count: number; average: number }[]
  points: Point[]
}
export interface Match {
  id: string
  played_at: string
  protocol: string
  play: string
  difficulty: string
  result: Result
  scenario: string | null
  strategy: string | null
  initiator: string | null
  rounds: number | null
  kills: number | null
  coins: number | null
  suspected_exit: boolean
}
export interface MatchSummary extends Match { bond_layers: number }
export interface MatchDetail extends Match {
  sync_count: number | null
  trophies: number | null
  duration_seconds: number | null
  bonds: { name: string; layers: number }[]
  squad: { id: string; name: string; items: string[] }[]
  bosses: string[]
}
export interface MatchPage { page: number; pages: number; total: number; matches: MatchSummary[] }
export interface ImportJob {
  id: string
  status: 'pending' | 'done' | 'failed'
  total: number
  processed: number
  error: string | null
  created_at: string
  completed_at: string | null
}
