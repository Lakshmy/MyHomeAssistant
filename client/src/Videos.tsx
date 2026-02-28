import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const API_URL = import.meta.env.VITE_API_URL || 'https://app-memory-backend.purplebeach-2b0b36ce.eastus.azurecontainerapps.io'

interface VideoItem {
  name: string
  size: number
  last_modified: string | null
  has_index: boolean
}

interface IndexEntry {
  object: string
  location: string
  room: string
  notes: string
  timestamp_start?: number | null
}

export default function Videos() {
  const navigate = useNavigate()
  const [videos, setVideos] = useState<VideoItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [playing, setPlaying] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Index panel state
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [indexData, setIndexData] = useState<Record<string, IndexEntry[]>>({})
  const [indexLoading, setIndexLoading] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState<string | null>(null)
  const [editBuffer, setEditBuffer] = useState<IndexEntry[]>([])
  const [saving, setSaving] = useState(false)

  const fetchVideos = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/videos`)
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()
      setVideos(data)
      setSelected(new Set())
      setPlaying(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load videos')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchVideos() }, [])

  const toggleSelect = (name: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(name)) {
        next.delete(name)
        if (playing === name) setPlaying(null)
      } else {
        next.add(name)
      }
      return next
    })
  }

  const handlePlay = () => {
    if (selected.size !== 1) return
    const name = [...selected][0]
    setPlaying(prev => (prev === name ? null : name))
  }

  const handleDelete = async () => {
    if (selected.size === 0) return
    const count = selected.size
    if (!confirm(`Delete ${count} video${count > 1 ? 's' : ''}? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await Promise.all([...selected].map(name =>
        fetch(`${API_URL}/videos/${encodeURIComponent(name)}`, { method: 'DELETE' })
      ))
      setVideos(v => v.filter(x => !selected.has(x.name)))
      if (playing && selected.has(playing)) setPlaying(null)
      setSelected(new Set())
      // Clear cached index data for deleted videos
      setIndexData(prev => {
        const next = { ...prev }
        selected.forEach(n => delete next[n])
        return next
      })
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  const toggleExpand = async (name: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(name)) {
        next.delete(name)
        return next
      }
      next.add(name)
      return next
    })
    // Load index if not cached
    if (!indexData[name]) {
      setIndexLoading(prev => new Set(prev).add(name))
      try {
        const res = await fetch(`${API_URL}/videos/${encodeURIComponent(name)}/index`)
        if (res.ok) {
          const data = await res.json()
          setIndexData(prev => ({ ...prev, [name]: data }))
        } else {
          setIndexData(prev => ({ ...prev, [name]: [] }))
        }
      } catch {
        setIndexData(prev => ({ ...prev, [name]: [] }))
      } finally {
        setIndexLoading(prev => { const n = new Set(prev); n.delete(name); return n })
      }
    }
  }

  const startEdit = (name: string) => {
    setEditing(name)
    setEditBuffer(JSON.parse(JSON.stringify(indexData[name] || [])))
  }

  const cancelEdit = () => { setEditing(null); setEditBuffer([]) }

  const updateEditEntry = (i: number, field: keyof IndexEntry, value: string) => {
    setEditBuffer(prev => prev.map((e, idx) => idx === i ? { ...e, [field]: value } : e))
  }

  const addEditEntry = () => {
    setEditBuffer(prev => [...prev, { object: '', location: '', room: '', notes: '', timestamp_start: null }])
  }

  const removeEditEntry = (i: number) => {
    setEditBuffer(prev => prev.filter((_, idx) => idx !== i))
  }

  const saveIndex = async (name: string) => {
    setSaving(true)
    try {
      const res = await fetch(`${API_URL}/videos/${encodeURIComponent(name)}/index`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editBuffer),
      })
      if (!res.ok) throw new Error('Save failed')
      setIndexData(prev => ({ ...prev, [name]: editBuffer }))
      // Mark has_index true if entries exist
      setVideos(prev => prev.map(v => v.name === name ? { ...v, has_index: editBuffer.length > 0 } : v))
      setEditing(null)
      setEditBuffer([])
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const displayName = (name: string) => {
    const match = name.match(/^[0-9a-f-]{36}_(.+)$/i)
    return match ? match[1] : name
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const formatDate = (iso: string | null) => {
    if (!iso) return ''
    return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
  }

  const canPlay = selected.size === 1
  const canDelete = selected.size >= 1

  return (
    <div className="container">
      <header>
        <button className="back-btn" onClick={() => navigate('/')}>{'<'} Back</button>
        <h1>My Videos</h1>
      </header>

      <div className="videos-toolbar">
        <button className="vid-btn play-btn" disabled={!canPlay} onClick={handlePlay}>
          {playing ? '\u23F9 Close' : '\u25B6 Play'}
        </button>
        <button className="vid-btn delete-btn" disabled={!canDelete || deleting} onClick={handleDelete}>
          {deleting ? 'Deleting...' : `\uD83D\uDDD1 Delete${selected.size > 1 ? ` (${selected.size})` : ''}`}
        </button>
        <button className="vid-btn refresh-btn-sm" onClick={fetchVideos} title="Refresh">
          {String.fromCodePoint(0x1F504)}
        </button>
        {selected.size > 0 && (
          <span className="selection-count">{selected.size} selected</span>
        )}
      </div>

      <main className="videos-main">
        {loading && <p className="videos-status">Loading videos...</p>}
        {error && <p className="videos-status videos-error">{error}</p>}
        {!loading && !error && videos.length === 0 && (
          <p className="videos-status">No videos uploaded yet.</p>
        )}

        {videos.length > 0 && (
          <div className="video-list">
            {videos.map(v => {
              const isSelected = selected.has(v.name)
              const isPlaying = playing === v.name
              const isExpanded = expanded.has(v.name)
              const isIndexLoading = indexLoading.has(v.name)
              const entries: IndexEntry[] = indexData[v.name] || []
              const isEditing = editing === v.name

              return (
                <div key={v.name}>
                  {/* Video row */}
                  <div
                    className={`video-row${isSelected ? ' video-row-selected' : ''}`}
                    onClick={() => toggleSelect(v.name)}
                  >
                    <input
                      type="checkbox"
                      className="video-checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(v.name)}
                      onClick={e => e.stopPropagation()}
                    />
                    <span className="video-icon">{String.fromCodePoint(0x1F3AC)}</span>
                    <div className="video-info">
                      <span className="video-name">
                        {displayName(v.name)}
                        {v.has_index && (
                          <span className="index-badge" title="Inventory indexed">
                            {String.fromCodePoint(0x1F4CB)}
                          </span>
                        )}
                      </span>
                      <span className="video-meta">{formatDate(v.last_modified)} &middot; {formatSize(v.size)}</span>
                    </div>
                    <button
                      className="expand-btn"
                      onClick={e => { e.stopPropagation(); toggleExpand(v.name) }}
                      title={isExpanded ? 'Hide index' : 'View/edit index'}
                    >
                      {isExpanded ? '\u25B2' : '\u25BC'}
                    </button>
                  </div>

                  {/* Video player */}
                  {isPlaying && (
                    <video
                      className="video-player"
                      controls
                      autoPlay
                      src={`${API_URL}/videos/${encodeURIComponent(v.name)}/stream`}
                    />
                  )}

                  {/* Index panel */}
                  {isExpanded && (
                    <div className="index-panel">
                      {isIndexLoading && <p className="index-loading">Loading index...</p>}

                      {!isIndexLoading && !isEditing && (
                        <>
                          {entries.length === 0 ? (
                            <p className="index-empty">No index yet for this video.</p>
                          ) : (
                            <ul className="index-list">
                              {entries.map((e, i) => (
                                <li key={i} className="index-entry">
                                  <span className="index-obj">{e.object}</span>
                                  <span className="index-loc">
                                    {e.location}{e.room ? ` · ${e.room}` : ''}{e.notes ? ` · ${e.notes}` : ''}{e.timestamp_start != null ? ` · @${e.timestamp_start}s` : ''}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          )}
                          <button className="index-edit-btn" onClick={() => startEdit(v.name)}>
                            {String.fromCodePoint(0x270F)} Edit Index
                          </button>
                        </>
                      )}

                      {!isIndexLoading && isEditing && (
                        <div className="index-editor">
                          <div className="index-editor-header">
                            <span>Edit inventory index</span>
                            <button className="index-add-btn" onClick={addEditEntry}>+ Add Item</button>
                          </div>
                          {editBuffer.map((e, i) => (
                            <div key={i} className="index-entry-edit">
                              <input
                                className="index-input"
                                placeholder="Object"
                                value={e.object}
                                onChange={ev => updateEditEntry(i, 'object', ev.target.value)}
                              />
                              <input
                                className="index-input"
                                placeholder="Location (e.g. top shelf)"
                                value={e.location}
                                onChange={ev => updateEditEntry(i, 'location', ev.target.value)}
                              />
                              <input
                                className="index-input"
                                placeholder="Room"
                                value={e.room}
                                onChange={ev => updateEditEntry(i, 'room', ev.target.value)}
                              />
                              <input
                                className="index-input"
                                placeholder="Notes (colour, brand...)"
                                value={e.notes}
                                onChange={ev => updateEditEntry(i, 'notes', ev.target.value)}
                              />
                              <input
                                className="index-input"
                                type="number"
                                placeholder="Timestamp (seconds)"
                                value={e.timestamp_start ?? ''}
                                onChange={ev => {
                                  const val = ev.target.value === '' ? null : Number(ev.target.value)
                                  setEditBuffer(prev => prev.map((entry, idx) => idx === i ? { ...entry, timestamp_start: val } : entry))
                                }}
                                style={{ maxWidth: '120px' }}
                              />
                              <button className="index-remove-btn" onClick={() => removeEditEntry(i)}>
                                {String.fromCodePoint(0x1F5D1)}
                              </button>
                            </div>
                          ))}
                          <div className="index-editor-actions">
                            <button className="index-save-btn" onClick={() => saveIndex(v.name)} disabled={saving}>
                              {saving ? 'Saving...' : `${String.fromCodePoint(0x1F4BE)} Save`}
                            </button>
                            <button className="index-cancel-btn" onClick={cancelEdit} disabled={saving}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </main>
    </div>
  )
}