import { Link } from 'react-router-dom'
import { SiteHeader } from '../components/SiteHeader'
import { useAuth } from '../auth/AuthContext'

const STEPS = [
  {
    title: 'Paste a public GitHub URL',
    body: 'RepoLens accepts public repositories only. Save a GitHub PAT on your profile when you are ready to open PRs.',
  },
  {
    title: 'Local AI review',
    body: 'Source is filtered and chunked, then scored by your local Ollama model — structured findings, never code execution.',
  },
  {
    title: 'Fix, chat, and open a PR',
    body: 'Ask about each finding, generate a code fix, and raise a pull request using the token saved on your profile.',
  },
]

const LENSES = [
  { name: 'Full', detail: 'Bugs, security, quality, and architecture together' },
  { name: 'Security', detail: 'Secrets, auth gaps, injection, unsafe config' },
  { name: 'Performance', detail: 'Hot paths, wasted work, inefficient calls' },
  { name: 'Quality', detail: 'Smells, naming, duplication, maintainability' },
  { name: 'Architecture', detail: 'Coupling, boundaries, scalability risks' },
]

export function LandingPage() {
  const { user } = useAuth()
  const primaryTo = user ? '/app' : '/register'

  return (
    <div className="shell shell--home">
      <SiteHeader />

      <main>
        <section className="hero">
          <div className="hero__plane" aria-hidden="true">
            <div className="hero__grid" />
            <div className="hero__orb hero__orb--a" />
            <div className="hero__orb hero__orb--b" />
            <pre className="hero__code">
              {`review(
  repo="owner/service",
  lens="security"
) → score 82`}
            </pre>
          </div>

          <div className="hero__content">
            <p className="brand-hero">RepoLens</p>
            <h1>Review, fix, and open PRs on public GitHub repos.</h1>
            <p className="hero__lede">
              Local AI findings you can chat about, turn into code fixes, and ship
              as pull requests — without ever executing repository code.
            </p>
            <div className="hero__actions">
              <Link to={primaryTo} className="btn btn--primary">
                {user ? 'Open workspace' : 'Start reviewing'}
              </Link>
              <a href="#how-it-works" className="btn btn--ghost">
                See how it works
              </a>
            </div>
          </div>
        </section>

        <section className="home-section home-section--what" aria-labelledby="what-heading">
          <p className="eyebrow">What this website does</p>
          <h2 id="what-heading">From review findings to a ready pull request.</h2>
          <p className="home-section__lede">
            RepoLens fetches public GitHub source, reviews it with your local LLM,
            and keeps findings in your workspace. Chat per issue, generate a fix,
            then open a PR with the GitHub token saved once on your profile.
          </p>
          <ul className="promise-list">
            <li>
              <strong>Structured reviews</strong>
              <span>Score, summary, languages, and severity-ranked issues</span>
            </li>
            <li>
              <strong>Per-finding chat & fixes</strong>
              <span>Ask follow-ups and generate proposed code changes per issue</span>
            </li>
            <li>
              <strong>Profile-stored GitHub PAT</strong>
              <span>Save a token once, encrypted, and reuse it to raise PRs</span>
            </li>
            <li>
              <strong>History & local model</strong>
              <span>Saved reviews reload fast; Ollama stays on your machine</span>
            </li>
          </ul>
        </section>

        <section
          id="how-it-works"
          className="home-section home-section--steps"
          aria-labelledby="how-heading"
        >
          <p className="eyebrow">How it works</p>
          <h2 id="how-heading">Three steps from URL to pull request.</h2>
          <ol className="step-flow">
            {STEPS.map((step, index) => (
              <li key={step.title} className="step-flow__item">
                <span className="step-flow__num" aria-hidden="true">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="home-section home-section--lenses" aria-labelledby="lenses-heading">
          <p className="eyebrow">Review lenses</p>
          <h2 id="lenses-heading">Choose what the model should focus on.</h2>
          <p className="home-section__lede">
            Pick a review type before analysis. RepoLens adapts the prompt so the
            model looks for the right class of problems.
          </p>
          <dl className="lens-list">
            {LENSES.map((lens) => (
              <div key={lens.name} className="lens-list__row">
                <dt>{lens.name}</dt>
                <dd>{lens.detail}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="home-section home-section--trust" aria-labelledby="trust-heading">
          <p className="eyebrow">Built for safe analysis</p>
          <h2 id="trust-heading">Public repos only. Source in, no code run.</h2>
          <p className="home-section__lede">
            RepoLens never installs dependencies, never shells out into repository
            scripts, and never sends `.env` or obvious secret files to the model.
            Your GitHub PAT is stored encrypted on your profile and never returned
            by the API.
          </p>
        </section>

        <section className="home-cta" aria-labelledby="cta-heading">
          <div className="home-cta__inner">
            <p className="eyebrow">Ready</p>
            <h2 id="cta-heading">Review your next public repository.</h2>
            <p>
              Create an account, paste a GitHub URL, then fix findings and open PRs
              from your workspace.
            </p>
            <div className="cta-actions">
              <Link to={primaryTo} className="btn btn--primary">
                {user ? 'Go to workspace' : 'Create free account'}
              </Link>
              {!user ? (
                <Link to="/login" className="btn btn--ghost">
                  Sign in
                </Link>
              ) : null}
            </div>
          </div>
        </section>
      </main>

      <footer className="home-footer">
        <span>RepoLens</span>
        <span>Public GitHub analysis · Local LLM · Fixes & PRs</span>
      </footer>
    </div>
  )
}
