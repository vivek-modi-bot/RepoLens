export type ReviewType =
  | 'full'
  | 'security'
  | 'performance'
  | 'quality'
  | 'architecture'

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'

export interface User {
  id: number
  username: string
  email: string | null
  created_at: string
  github_token_configured?: boolean
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface ReviewIssue {
  file: string
  line: number | null
  severity: Severity
  category: string
  title: string
  description: string
  recommendation: string
}

export interface ReviewStatistics {
  files_analyzed: number
  languages: string[]
  issues_found: number
  total_lines: number
  chunks_processed: number
}

export interface ReviewResponse {
  review_id: string | null
  repository: string
  branch: string
  review_type: string
  overall_score: number
  summary: string
  statistics: ReviewStatistics
  issues: ReviewIssue[]
  created_at: string | null
  from_cache?: boolean
  chunks_reused?: boolean
  commit_sha?: string | null
}

export interface ReviewSummary {
  review_id: string
  repository: string
  branch: string
  review_type: string
  overall_score: number
  summary: string
  created_at: string
  issues_found: number
}

export interface ReviewMessage {
  id: string
  issue_index: number
  role: 'user' | 'assistant' | string
  content: string
  created_at: string
}

export interface ReviewAskResponse {
  review_id: string
  issue_index: number
  question: string
  answer: string
  messages: ReviewMessage[]
}

export interface FixSuggestion {
  fix_id: string
  review_id: string
  issue_index: number
  file_path: string
  original_content: string
  updated_content: string
  explanation: string
  commit_message: string
  pr_url: string | null
  pr_number: number | null
  created_at: string | null
}

export interface PullRequestResult {
  fix_id: string
  review_id: string
  issue_index: number
  branch_name: string
  pr_number: number
  pr_url: string
  commit_sha: string
}

export interface ApiErrorBody {
  error?: {
    code?: string
    message?: string
  }
  detail?: string
}
