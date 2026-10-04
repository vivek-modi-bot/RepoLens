import type {
  ApiErrorBody,
  FixSuggestion,
  PullRequestResult,
  ReviewAskResponse,
  ReviewMessage,
  ReviewResponse,
  ReviewSummary,
  ReviewType,
  TokenResponse,
  User,
} from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    let message = 'Request failed'
    let code: string | undefined
    try {
      const body = (await response.json()) as ApiErrorBody
      message = body.error?.message || body.detail || message
      code = body.error?.code
    } catch {
      // ignore JSON parse failures
    }
    throw new ApiError(message, response.status, code)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  register(username: string, password: string, email?: string) {
    return request<User>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password, email: email || null }),
    })
  },

  login(username: string, password: string) {
    return request<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },

  me(token: string) {
    return request<User>('/api/v1/auth/me', {}, token)
  },

  updateProfile(
    token: string,
    payload: {
      email?: string | null
      github_token?: string
      clear_github_token?: boolean
    },
  ) {
    return request<User>(
      '/api/v1/auth/me',
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      },
      token,
    )
  },

  health() {
    return request<{ status: string; llm_available: boolean }>('/api/v1/health')
  },

  reviewRepository(
    token: string,
    payload: {
      repository_url: string
      branch?: string
      review_type: ReviewType
      force_refresh?: boolean
    },
  ) {
    return request<ReviewResponse>(
      '/api/v1/repository/review',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      token,
    )
  },

  listReviews(token: string) {
    return request<ReviewSummary[]>('/api/v1/repository/reviews', {}, token)
  },

  getReview(token: string, reviewId: string) {
    return request<ReviewResponse>(`/api/v1/repository/${reviewId}`, {}, token)
  },

  listMessages(token: string, reviewId: string, issueIndex: number) {
    return request<ReviewMessage[]>(
      `/api/v1/repository/${reviewId}/messages?issue_index=${issueIndex}`,
      {},
      token,
    )
  },

  askQuestion(
    token: string,
    reviewId: string,
    question: string,
    issueIndex: number,
  ) {
    return request<ReviewAskResponse>(
      `/api/v1/repository/${reviewId}/ask`,
      {
        method: 'POST',
        body: JSON.stringify({ question, issue_index: issueIndex }),
      },
      token,
    )
  },

  generateFindingFix(token: string, reviewId: string, issueIndex: number) {
    return request<FixSuggestion>(
      `/api/v1/repository/${reviewId}/findings/${issueIndex}/fix`,
      { method: 'POST' },
      token,
    )
  },

  getFindingFix(token: string, reviewId: string, issueIndex: number) {
    return request<FixSuggestion>(
      `/api/v1/repository/${reviewId}/findings/${issueIndex}/fix`,
      {},
      token,
    )
  },

  createFindingPullRequest(
    token: string,
    reviewId: string,
    issueIndex: number,
    payload: {
      github_token?: string
      fix_id?: string
      branch_name?: string
      pr_title?: string
      pr_body?: string
    },
  ) {
    return request<PullRequestResult>(
      `/api/v1/repository/${reviewId}/findings/${issueIndex}/pull-request`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      token,
    )
  },
}
