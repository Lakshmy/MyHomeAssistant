import { useState } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import Chat from './Chat'
import Record from './Record'
import Videos from './Videos'
import './App.css'

function Home() {
  const navigate = useNavigate()
  const [adminMode, setAdminMode] = useState(() => localStorage.getItem('adminMode') === 'true')

  const toggleAdmin = () => {
    setAdminMode(v => {
      const next = !v
      localStorage.setItem('adminMode', String(next))
      return next
    })
  }

  return (
    <div className="container">
      <header>
        <div className="header-row">
          <h1>Memory Assistant</h1>
          <div className="admin-toggle-row">
            <span className="admin-toggle-label">Admin</span>
            <button
              className={`toggle-btn${adminMode ? ' toggle-btn-on' : ''}`}
              onClick={toggleAdmin}
              aria-pressed={adminMode}
            >
              <span className="toggle-thumb" />
            </button>
          </div>
        </div>
      </header>

      <main>
        <div className="action-grid">
          <button className="large-btn primary-btn" onClick={() => navigate('/chat')}>
            <span className="icon">🎤</span>
            Ask Question
          </button>

          {adminMode && (
            <>
              <button className="large-btn secondary-btn" onClick={() => navigate('/record')}>
                <span className="icon">{String.fromCodePoint(0x1F4F9)}</span>
                Upload Videos
              </button>

              <button className="large-btn tertiary-btn" onClick={() => navigate('/videos')}>
                <span className="icon">{String.fromCodePoint(0x1F3AC)}</span>
                My Videos
              </button>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/chat" element={<Chat />} />
      <Route path="/record" element={<Record />} />
      <Route path="/videos" element={<Videos />} />
    </Routes>
  )
}

export default App
