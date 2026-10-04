import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { ReviewResults } from '../components/ReviewResults'
import { SiteHeader } from '../components/SiteHeader'
import type { ReviewResponse, ReviewSummary, ReviewType } from '../types'

const REVIEW_TYPES: { value: ReviewType; label: string; hint: string }[] = [
  { value: 'full', label: 'Full', hint: 'Bugs, security, quality, architecture' },
  { value: 'security', label: 'Security', hint: 'Secrets, auth, injection risks' },
  { value: 'performance', label: 'Performance', hint: 'Hot paths and wasteful work' },
  { value: 'quality', label: 'Quality', hint: 'Smells, naming, maintainability' },
  { value: 'architecture', label: 'Architecture', hint: 'Coupling and boundaries' },
]

export function WorkspacePage() {
  const { token, user } = useAuth()
  const [repositoryUrl, setRepositoryUrl] = useState(
    'https://github.com/psf/requests',
  )
  const [branch, setBranch] = useState('main')
  const [reviewType, setReviewType] = useState<ReviewType>('full')
  const [forceRefresh, setForceRefresh] = useState(false)
  const [health, setHealth] = useState<{
    status: string
    llm_available: boolean
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [review, setReview] = useState<ReviewResponse | null>(null)
  const [history, setHistory] = useState<ReviewSummary[]>([])

  const refreshHistory = useCallback(async () => {
    if (!token) return
    try {
      const rows = await api.listReviews(token)
      setHistory(rows)
    } catch {
      setHistory([])
    }
  }, [token])

  useEffect(() => {
    let cancelled = false
    api
      .health()
      .then((data) => {
        if (!cancelled) setHealth(data)
      })
      .catch(() => {
        if (!cancelled) setHealth({ status: 'down', llm_available: false })
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    void refreshHistory()
  }, [refreshHistory])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!token) return
    setError(null)
    setSubmitting(true)
    setReview(null)
    try {
      const result = await api.reviewRepository(token, {
        repository_url: repositoryUrl.trim(),
        branch: branch.trim() || undefined,
        review_type: reviewType,
        force_refresh: forceRefresh,
      })
      setReview(result)
      await refreshHistory()
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Review failed. Check the API and Ollama services.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function openHistoryItem(item: ReviewSummary) {
    if (!token) return
    setError(null)
    try {
      const full = await api.getReview(token, item.review_id)
      setReview({ ...full, from_cache: true })
      setRepositoryUrl(`https://github.com/${item.repository}`)
      setBranch(item.branch)
      setReviewType(item.review_type as ReviewType)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load review')
    }
  }

  return (
    <div className="shell shell--app">
      <SiteHeader />
      <main className="workspace workspace--split">
        <aside className="history-panel">
          <p className="eyebrow">History</p>
          <h2>Previous reviews</h2>
          {history.length === 0 ? (
            <p className="empty">No saved reviews yet.</p>
          ) : (
            <ul className="history-list">
              {history.map((item) => (
                <li key={item.review_id}>
                  <button
                    type="button"
                    className={`history-item ${
                      review?.review_id === item.review_id
                        ? 'history-item--active'
                        : ''
                    }`}
                    onClick={() => void openHistoryItem(item)}
                  >
                    <span className="history-item__repo">{item.repository}</span>
                    <span className="history-item__meta">
                      {item.review_type} · score {item.overall_score} ·{' '}
                      {item.issues_found} issues
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className="workspace__main">
          <section className="workspace__intro">
            <p className="eyebrow">Workspace</p>
            <h1>Review a public repository</h1>
            <p>
              Hello {user?.username}. Saved reviews reload instantly. Unchanged
              commits reuse cached chunks so RepoLens does not re-chunk again.
            </p>
            {health ? (
              <p
                className={`health-chip ${
                  health.llm_available ? 'health-chip--ok' : 'health-chip--warn'
                }`}
              >
                API {health.status}
                {health.llm_available ? ' · LLM ready' : ' · LLM unavailable'}
              </p>
            ) : null}
          </section>

          <form className="review-form" onSubmit={onSubmit}>
            <label>
              Repository URL
              <input
                value={repositoryUrl}
                onChange={(e) => setRepositoryUrl(e.target.value)}
                placeholder="https://github.com/owner/repository"
                required
              />
            </label>

            <div className="review-form__row">
              <label>
                Branch
                <input
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                  placeholder="main"
                />
              </label>
            </div>

            <fieldset>
              <legend>Review type</legend>
              <div className="type-grid" role="radiogroup" aria-label="Review type">
                {REVIEW_TYPES.map((type) => (
                  <label
                    key={type.value}
                    className={`type-option ${
                      reviewType === type.value ? 'type-option--active' : ''
                    }`}
                  >
                    <input
                      type="radio"
                      name="review_type"
                      value={type.value}
                      checked={reviewType === type.value}
                      onChange={() => setReviewType(type.value)}
                    />
                    <span className="type-option__label">{type.label}</span>
                    <span className="type-option__hint">{type.hint}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={forceRefresh}
                onChange={(e) => setForceRefresh(e.target.checked)}
              />
              Force re-analyze (ignore saved review for this repo/type)
            </label>

            {error ? <p className="form-error">{error}</p> : null}

            <button className="btn btn--primary" type="submit" disabled={submitting}>
              {submitting ? 'Analyzing repository…' : 'Run AI review'}
            </button>
            {submitting ? (
              <p className="form-hint">
                First run analyzes chunks. Later runs reuse saved reviews/chunks when
                possible.
              </p>
            ) : null}
          </form>

          {review ? <ReviewResults review={review} token={token} /> : null}
        </div>
      </main>
    </div>
  )
}
