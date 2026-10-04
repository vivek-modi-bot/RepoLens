import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { FixSuggestion, PullRequestResult } from '../types'

export function FindingFixPanel({
  token,
  reviewId,
  issueIndex,
}: {
  token: string
  reviewId: string
  issueIndex: number
}) {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [fix, setFix] = useState<FixSuggestion | null>(null)
  const [pr, setPr] = useState<PullRequestResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [creatingPr, setCreatingPr] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    api
      .getFindingFix(token, reviewId, issueIndex)
      .then((data) => {
        if (!cancelled) {
          setFix(data)
          if (data.pr_url) {
            setPr({
              fix_id: data.fix_id,
              review_id: data.review_id,
              issue_index: data.issue_index,
              branch_name: '',
              pr_number: data.pr_number || 0,
              pr_url: data.pr_url,
              commit_sha: '',
            })
          }
        }
      })
      .catch(() => {
        if (!cancelled) setFix(null)
      })
    return () => {
      cancelled = true
    }
  }, [open, token, reviewId, issueIndex])

  async function generateFix() {
    setGenerating(true)
    setError(null)
    setPr(null)
    try {
      const data = await api.generateFindingFix(token, reviewId, issueIndex)
      setFix(data)
      setOpen(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to generate fix')
    } finally {
      setGenerating(false)
    }
  }

  async function createPr(event: FormEvent) {
    event.preventDefault()
    if (!fix) return
    setCreatingPr(true)
    setError(null)
    try {
      const result = await api.createFindingPullRequest(
        token,
        reviewId,
        issueIndex,
        {
          fix_id: fix.fix_id,
        },
      )
      setPr(result)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Unable to create pull request',
      )
    } finally {
      setCreatingPr(false)
    }
  }

  return (
    <div className="finding-fix">
      <div className="finding-fix__actions">
        <button
          type="button"
          className="btn btn--primary btn--small"
          onClick={() => void generateFix()}
          disabled={generating}
        >
          {generating ? 'Generating fix…' : 'Generate code fix'}
        </button>
        {fix ? (
          <button
            type="button"
            className="btn btn--ghost btn--small"
            onClick={() => setOpen((value) => !value)}
          >
            {open ? 'Hide fix' : 'Show fix'}
          </button>
        ) : null}
      </div>

      {open && fix ? (
        <div className="finding-fix__panel">
          <p className="form-hint">
            Suggested change for <code>{fix.file_path}</code>
          </p>
          <p>{fix.explanation}</p>
          <p className="form-hint">
            Commit message: <strong>{fix.commit_message}</strong>
          </p>

          <div className="diff-grid">
            <div>
              <h4>Current</h4>
              <pre className="code-block">{fix.original_content}</pre>
            </div>
            <div>
              <h4>Proposed</h4>
              <pre className="code-block code-block--proposed">
                {fix.updated_content}
              </pre>
            </div>
          </div>

          {pr?.pr_url ? (
            <p className="pr-success">
              Pull request ready:{' '}
              <a href={pr.pr_url} target="_blank" rel="noreferrer">
                #{pr.pr_number || 'PR'} {pr.pr_url}
              </a>
            </p>
          ) : (
            <form className="pr-form" onSubmit={createPr}>
              {user?.github_token_configured ? (
                <p className="form-hint">
                  Using the GitHub token saved in your{' '}
                  <Link to="/profile">profile</Link>.
                </p>
              ) : (
                <p className="form-hint profile-pat-nudge">
                  GitHub PAT required.{' '}
                  <Link to="/profile">Save a token in your profile</Link> before
                  raising a pull request.
                </p>
              )}
              <button
                className="btn btn--primary btn--small"
                type="submit"
                disabled={creatingPr || !user?.github_token_configured}
              >
                {creatingPr ? 'Opening PR…' : 'Raise pull request'}
              </button>
            </form>
          )}
        </div>
      ) : null}

      {error ? <p className="form-error">{error}</p> : null}
    </div>
  )
}
