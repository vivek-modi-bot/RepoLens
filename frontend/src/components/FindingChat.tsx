import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { ReviewMessage } from '../types'

export function FindingChat({
  token,
  reviewId,
  issueIndex,
  findingTitle,
}: {
  token: string
  reviewId: string
  issueIndex: number
  findingTitle: string
}) {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ReviewMessage[]>([])
  const [question, setQuestion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [asking, setAsking] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    api
      .listMessages(token, reviewId, issueIndex)
      .then((rows) => {
        if (!cancelled) setMessages(rows)
      })
      .catch(() => {
        if (!cancelled) setMessages([])
      })
    return () => {
      cancelled = true
    }
  }, [token, reviewId, issueIndex, open])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed) return
    setAsking(true)
    setError(null)
    try {
      const result = await api.askQuestion(token, reviewId, trimmed, issueIndex)
      setMessages(result.messages)
      setQuestion('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to ask question')
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className="finding-chat">
      <button
        type="button"
        className="btn btn--ghost btn--small"
        onClick={() => setOpen((value) => !value)}
      >
        {open ? 'Hide chat' : 'Ask about this finding'}
      </button>

      {open ? (
        <div className="finding-chat__panel">
          <p className="form-hint">
            Chat is scoped to: <strong>{findingTitle}</strong>
          </p>

          {!user?.github_token_configured ? (
            <p className="form-hint profile-pat-nudge">
              No GitHub PAT saved yet.{' '}
              <Link to="/profile">Add one in your profile</Link> so you can raise
              pull requests from findings.
            </p>
          ) : null}

          <div className="chat__thread" aria-live="polite">
            {messages.length === 0 ? (
              <p className="empty">
                Ask how to fix this, why it matters, or what to check next.
              </p>
            ) : (
              messages.map((message) => (
                <div
                  key={message.id}
                  className={`chat__bubble chat__bubble--${message.role}`}
                >
                  <span className="chat__role">
                    {message.role === 'user' ? 'You' : 'RepoLens'}
                  </span>
                  <p>{message.content}</p>
                </div>
              ))
            )}
          </div>

          <form className="chat__form" onSubmit={onSubmit}>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about this finding…"
              minLength={3}
              required
            />
            <button className="btn btn--primary btn--small" type="submit" disabled={asking}>
              {asking ? '…' : 'Ask'}
            </button>
          </form>
          {error ? <p className="form-error">{error}</p> : null}
        </div>
      ) : null}
    </div>
  )
}
