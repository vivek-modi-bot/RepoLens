import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { SiteHeader } from '../components/SiteHeader'

export function ProfilePage() {
  const { token, user, refreshProfile } = useAuth()
  const [email, setEmail] = useState(user?.email || '')
  const [githubToken, setGithubToken] = useState('')
  const [clearToken, setClearToken] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!token) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      await api.updateProfile(token, {
        email: email.trim() || null,
        github_token: clearToken ? undefined : githubToken.trim() || undefined,
        clear_github_token: clearToken,
      })
      await refreshProfile()
      setGithubToken('')
      setClearToken(false)
      setMessage('Profile saved.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to update profile')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="shell shell--app">
      <SiteHeader />
      <main className="auth-panel" style={{ width: 'min(640px, 100%)' }}>
        <div className="auth-panel__intro">
          <p className="eyebrow">Profile</p>
          <h1>Account settings</h1>
          <p>
            Save a GitHub personal access token once and reuse it for raising pull
            requests on findings.
          </p>
        </div>

        <form className="form" onSubmit={onSubmit}>
          <label>
            Username
            <input type="text" value={user?.username || ''} disabled />
          </label>

          <label>
            Email <span className="optional">(optional)</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </label>

          <div className="profile-token">
            <p className="form-hint">
              GitHub token status:{' '}
              <strong>
                {user?.github_token_configured ? 'Configured' : 'Not set'}
              </strong>
            </p>

            <div className="pat-howto">
              <h2>How to create a GitHub PAT</h2>
              <ol>
                <li>
                  Open{' '}
                  <a
                    href="https://github.com/settings/tokens"
                    target="_blank"
                    rel="noreferrer"
                  >
                    GitHub → Settings → Developer settings → Personal access tokens
                  </a>
                </li>
                <li>
                  Choose <strong>Tokens (classic)</strong> →{' '}
                  <strong>Generate new token (classic)</strong>
                </li>
                <li>
                  Give it a note (e.g. <code>RepoLens</code>) and set an expiration
                </li>
                <li>
                  Under scopes, enable <strong>repo</strong> (full control of private
                  repositories — required to push branches and open PRs)
                </li>
                <li>
                  Click <strong>Generate token</strong>, copy the value (starts with{' '}
                  <code>ghp_</code>), and paste it below. GitHub only shows it once.
                </li>
              </ol>
              <p className="form-hint">
                Prefer fine-grained tokens? Create one with access to the target
                repositories and permissions: <strong>Contents: Read and write</strong>,{' '}
                <strong>Pull requests: Read and write</strong>.
              </p>
            </div>

            <label>
              GitHub personal access token
              <input
                type="password"
                value={githubToken}
                onChange={(e) => {
                  setGithubToken(e.target.value)
                  if (e.target.value) setClearToken(false)
                }}
                placeholder={
                  user?.github_token_configured
                    ? '•••••••• (leave blank to keep current)'
                    : 'ghp_••••••••'
                }
                autoComplete="off"
                disabled={clearToken}
              />
            </label>
            <p className="form-hint">
              Stored encrypted on the server and never returned by the API.
            </p>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={clearToken}
                onChange={(e) => {
                  setClearToken(e.target.checked)
                  if (e.target.checked) setGithubToken('')
                }}
              />
              Remove saved GitHub token
            </label>
          </div>

          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="pr-success">{message}</p> : null}

          <button className="btn btn--primary" type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save profile'}
          </button>
        </form>
      </main>
    </div>
  )
}
