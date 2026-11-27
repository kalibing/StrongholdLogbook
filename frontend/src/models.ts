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
export interface Peak { layers: number; names: string[] }
export interface Point {
  match_id?: string | null
  label: string
  result: Result | null
  wins?: number
  losses?: number
  layers: number
  peak: Peak | null
  average_bond_layers?: number | null
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
export interface StrategyStat {
  /** 记录里的原值：可能是 band id，也可能是策略名 */
  name: string
  count: number
  wins: number
  losses: number
  usage_rate: number
  win_rate: number
}
export interface TrophyBadge { icon: string | null; level: number | null }
export interface Overview {
  trophy_change: number | null
  trophy_badge: TrophyBadge | null
  /** 账号累计奖杯：profile 来自成就档案，matches 为导入对局的奖杯记录累加（旧后端没有此字段） */
  trophy_total?: { total: number; source: 'profile' | 'matches' } | null
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
  /** 旧后端没有这个字段 */
  strategies?: { name: string; count: number; wins: number; win_rate: number }[]
  bonds: { name: string; count: number; average: number }[]
  bond_layers: BondLayers[]
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
export interface BondLayers { name: string; layers: number }
export interface MatchSummary extends Match {
  bond_layers: number
  bonds?: BondLayers[]
  bosses?: string[]
}
export interface MatchDetail extends Match {
  sync_count: number | null
  trophies: number | null
  duration_seconds: number | null
  bonds: BondLayers[]
  squad: { id: string; name: string; items: string[]; elite?: boolean | null; evolve?: number | null }[]
  bosses: string[]
}
export interface MatchPage { page: number; pages: number; total: number; matches: MatchSummary[] }
export interface ReviewMetrics { matches: number; average_layers: number | null; average_rounds: number | null }
type ReviewMatch = Pick<Match, 'id' | 'played_at' | 'play' | 'difficulty' | 'rounds'>
export interface DailyReview {
  bonds: BondLayers[]
  wins: ReviewMetrics
  losses: ReviewMetrics
  boss_matches: number
  normal_matches: number
  hidden_matches: number
  bosses: { name: string; matches: number; hidden: boolean }[]
  longest_win_streak: number
  total_duration_seconds: number | null
  latest_loss: ReviewMatch | null
  most_kills: (ReviewMatch & { kills: number }) | null
  /** 旧后端没有这两项 */
  most_layers?: (ReviewMatch & { layers: number }) | null
  most_coins?: (ReviewMatch & { coins: number }) | null
  ai_available: boolean
}
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
  /** 其中击破隐藏首领、普通首领，以及击破首领后落败的场次 */
  hidden?: number
  normal_boss?: number
  boss_losses?: number
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
  trophy: TrophyBadge & { total: number }
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

/** 「我的主页」：账号生涯汇总（/api/profile），不受筛选影响。 */
export interface Profile {
  username: string
  account: { nickname: string | null; nick_number: string | null; level: number | null; likes: number | null; titles: number } | null
  trophy_badge: TrophyBadge | null
  trophy_total: { total: number; source: 'profile' | 'matches' } | null
  career: {
    matches: number
    wins: number
    losses: number
    win_rate: number | null
    excluded: number
    first_day: string | null
    last_day: string | null
    active_days: number
    play_seconds: number | null
    total_kills: number | null
    max_kills: number | null
    max_layers: number | null
  }
  streaks: { best_win: number; current: { result: Result; count: number } | null }
  best: { union: string | null; solo: string | null }
  plays: { play: string; matches: number; wins: number }[]
  operators: Operator[]
  strategies: { name: string; count: number; wins: number; win_rate: number }[]
  recent_results: Result[]
  activity: { start: string; end: string; days: { day: string; count: number }[] }
}
