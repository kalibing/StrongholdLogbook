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
  squad: { id: string; name: string; items: string[]; elite?: boolean | null; evolve?: number | null }[]
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

export interface DistributionBucket {
  label: string
  wins: number
  losses: number
  total: number
}
export interface DistributionGroup {
  play: string
  buckets: DistributionBucket[]
}

export interface AchvTitle {
  id: string
  name: string
  type: string
  type_name: string
  rank: number
  group: 'overview' | 'special'
  value: number
  pic_id: string | null
}
export interface AchvDimension {
  key: string
  name: string
  score: number
  titles: AchvTitle[]
}
export interface AchvPlayer {
  uid: string
  nickname: string | null
  nick_number: string | null
  level: number | null
  avatar: string | null
  name_card: string | null
}
export interface AchvTeammate {
  uid: string
  nickname: string | null
  nick_number: string | null
  level: number | null
  avatar: string | null
  name_card: string | null
  plays: number | null
  wins: number | null
}

export interface AchvSocial {
  likes: number
  friends: number
  star_friends: string[]
  best_teammate: AchvTeammate | null
  top_teammates?: AchvTeammate[]
}
export interface AchvBandTop {
  id: string
  name: string | null
  effect: string | null
  value: number
  winning_rate: number | null
  type: string | null
}
export interface AchvBadge {
  id: string
  name: string | null
  effect: string | null
  type: string | null
  variant: 'master' | 'base'
  variant_name: string
  obtained: boolean
  icon: string | null
}
export interface AchvBands {
  top: AchvBandTop[]
  badges: AchvBadge[]
  variants: Record<string, string>
  summary: { total: number; mastered: number; pending: number }
}
export interface AchvBest { key: string; label: string; value: number }
export interface AchvModes {
  single: { battle: number; win: number; hard_mode: string | null; hard_win: number }
  multi: { battle: number; win: number; hard_win: number; second_hard_win: number }
}
export interface AchvSeason {
  activity: string | null
  version: string | null
  name: string | null
  year: string | null
  start: string | null
  end: string | null
  offseason: boolean
}
export interface AchvProfile {
  player: AchvPlayer
  trophy: { total: number; level: number; icon: string | null }
  likes: number
  dimensions: AchvDimension[]
  titles: AchvTitle[]
  social: AchvSocial
  modes: AchvModes
  best: AchvBest[]
  bands: AchvBands
  season: AchvSeason
  fetched_at: string
  warnings?: string[]
}
export interface AchvState {
  connected: boolean
  source: string | null
  uid: string | null
  nickname: string | null
  fetched_at: string | null
  stale: boolean
  phone: string | null
}
export interface AchvEnvelope {
  state: AchvState
  warning?: string | null
  warnings?: string[]
  data: AchvProfile
}
