export type Severity = 'ERROR' | 'WARNING' | 'INFO'

export type ReviewType = 'all' | 'security' | 'performance' | 'bugs'

export interface PRMeta {
  pr_title?: string
  author_name: string
  author_avatar: string
  updated_at: string
  created_at?: string
  commits: number
  base_branch: string
  head_branch: string
  additions: number
  deletions: number
  files_changed: number
  files: { filename: string; additions: number; deletions: number }[]
}

export interface ReviewIssue {
  severity: Severity
  file: string
  line?: number
  position?: number
  title: string
  description: string
  suggestion?: string
  diff_snippet?: string
  confidence?: number
}

export interface WalkthroughEntry {
  file: string
  summary: string
}

export interface ReviewResult {
  pr_url: string
  summary: string
  risk_level: 'HIGH' | 'MEDIUM' | 'LOW'
  walkthrough: WalkthroughEntry[]
  issues: ReviewIssue[]
  stats: {
    files_changed: number
    additions: number
    deletions: number
    issues_by_severity: Record<Severity, number>
  }
  priority_files?: string[]
  risk_areas?: RiskArea[]
  merge_recommendation?: MergeRecommendation
}

export interface RiskArea {
  level: 'HIGH' | 'MEDIUM' | 'LOW'
  file: string
  title: string
  impact: string
}

export interface MergeRecommendation {
  decision: 'APPROVE' | 'REQUEST_CHANGES' | 'COMMENT'
  confidence: number
  reasons: string[]
}

export interface ReviewRequest {
  pr_url: string
  github_token?: string
  options?: {
    include_style: boolean
    context_lines: number
  }
}
