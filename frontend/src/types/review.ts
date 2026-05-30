export type Severity = 'ERROR' | 'WARNING' | 'INFO'

export interface ReviewIssue {
  severity: Severity
  file: string
  line?: number
  position?: number
  title: string
  description: string
  suggestion?: string
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
}

export interface ReviewRequest {
  pr_url: string
  github_token?: string
  options?: {
    include_style: boolean
    context_lines: number
  }
}
