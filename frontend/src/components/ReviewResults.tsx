import type { ReviewIssue, ReviewResponse, Severity } from '../types'
import { FindingChat } from './FindingChat'
import { FindingFixPanel } from './FindingFix'

const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'info']

function scoreTone(score: number): string {
  if (score >= 85) return 'score--good'
  if (score >= 65) return 'score--ok'
  return 'score--warn'
}

function IssueRow({
  issue,
  issueIndex,
  token,
  reviewId,
}: {
  issue: ReviewIssue
  issueIndex: number
  token: string | null
  reviewId: string | null
}) {
  return (
    <article className="issue">
      <div className="issue__meta">
        <span className={`severity severity--${issue.severity}`}>
          {issue.severity}
        </span>
        <span className="issue__category">{issue.category}</span>
      </div>
      <h3>{issue.title}</h3>
      <p className="issue__file">
        {issue.file}
        {issue.line ? `:${issue.line}` : ''}
      </p>
      <p>{issue.description}</p>
      <p className="issue__rec">
        <strong>Recommendation:</strong> {issue.recommendation}
      </p>
      {token && reviewId ? (
        <>
          <FindingFixPanel
            token={token}
            reviewId={reviewId}
            issueIndex={issueIndex}
          />
          <FindingChat
            token={token}
            reviewId={reviewId}
            issueIndex={issueIndex}
            findingTitle={issue.title}
          />
        </>
      ) : null}
    </article>
  )
}

export function ReviewResults({
  review,
  token,
}: {
  review: ReviewResponse
  token: string | null
}) {
  const indexed = review.issues.map((issue, index) => ({ issue, index }))
  const sorted = [...indexed].sort(
    (a, b) =>
      SEVERITY_ORDER.indexOf(a.issue.severity) -
      SEVERITY_ORDER.indexOf(b.issue.severity),
  )

  return (
    <section className="results" aria-live="polite">
      <header className="results__header">
        <div>
          <p className="eyebrow">
            {review.from_cache ? 'Loaded from history' : 'Review complete'}
            {review.chunks_reused ? ' · chunks reused' : ''}
          </p>
          <h2>
            {review.repository}
            <span className="results__branch">@{review.branch}</span>
          </h2>
          <p className="results__summary">{review.summary}</p>
        </div>
        <div className={`score ${scoreTone(review.overall_score)}`}>
          <span className="score__value">{review.overall_score}</span>
          <span className="score__label">overall</span>
        </div>
      </header>

      <dl className="stat-row">
        <div>
          <dt>Files</dt>
          <dd>{review.statistics.files_analyzed}</dd>
        </div>
        <div>
          <dt>Issues</dt>
          <dd>{review.statistics.issues_found}</dd>
        </div>
        <div>
          <dt>Languages</dt>
          <dd>
            {review.statistics.languages.length
              ? review.statistics.languages.join(', ')
              : '—'}
          </dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{review.review_type}</dd>
        </div>
      </dl>

      <div className="issues">
        <h3 className="issues__heading">Findings</h3>
        <p className="form-hint">
          Each finding supports its own fix + PR flow and a scoped chat thread.
        </p>
        {sorted.length === 0 ? (
          <p className="empty">No issues reported for this review type.</p>
        ) : (
          sorted.map(({ issue, index }) => (
            <IssueRow
              key={`${issue.file}-${issue.title}-${index}`}
              issue={issue}
              issueIndex={index}
              token={token}
              reviewId={review.review_id}
            />
          ))
        )}
      </div>
    </section>
  )
}
