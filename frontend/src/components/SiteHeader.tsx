import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function SiteHeader() {
  const { user, logout } = useAuth()

  return (
    <header className="site-header">
      <Link to="/" className="brand-mark">
        <span className="brand-mark__glyph" aria-hidden="true" />
        RepoLens
      </Link>

      <nav className="site-nav" aria-label="Primary">
        {user ? (
          <>
            <NavLink to="/" end>
              Home
            </NavLink>
            <NavLink to="/app">Workspace</NavLink>
            <Link
              to="/profile"
              className="site-nav__user"
              title="Open profile"
            >
              {user.username}
            </Link>
            <button type="button" className="btn btn--ghost" onClick={logout}>
              Sign out
            </button>
          </>
        ) : (
          <>
            <a href="/#how-it-works">How it works</a>
            <NavLink to="/login">Sign in</NavLink>
            <Link to="/register" className="btn btn--primary btn--small">
              Get started
            </Link>
          </>
        )}
      </nav>
    </header>
  )
}
