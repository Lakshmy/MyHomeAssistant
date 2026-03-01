import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

const API_URL = import.meta.env.VITE_API_URL || ''

type Stage = 'idle' | 'selected' | 'uploading' | 'analyzing' | 'done' | 'error'

interface IndexEntry {
  object: string
  location: string
  room: string
  notes: string
  timestamp_start?: number | null
}

export default function Record() {
  const navigate = useNavigate()
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [stage, setStage] = useState<Stage>('idle')
  const [foundItems, setFoundItems] = useState<IndexEntry[]>([])
  const [errorMsg, setErrorMsg] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0]
      setVideoFile(file)
      setStage('selected')
      setFoundItems([])
      setErrorMsg('')
      if (videoRef.current) {
        videoRef.current.src = URL.createObjectURL(file)
      }
    }
  }

  const handleUpload = async () => {
    if (!videoFile) return

    setStage('uploading')
    setErrorMsg('')

    const formData = new FormData()
    formData.append('file', videoFile)

    try {
      const response = await fetch(`${API_URL}/analyze-video`, {
        method: 'POST',
        body: formData,
      })

      setStage('analyzing')

      if (!response.ok) throw new Error('Upload failed')

      const data = await response.json()
      if (data.error) throw new Error(data.error)

      setFoundItems(data.items || [])
      setStage('done')

      setTimeout(() => {
        setStage('idle')
        setVideoFile(null)
        setFoundItems([])
        if (videoRef.current) videoRef.current.src = ''
      }, 10000)

    } catch (error) {
      console.error(error)
      setErrorMsg(error instanceof Error ? error.message : 'Upload failed')
      setStage('error')
    }
  }

  const stageLabel: Record<Stage, string> = {
    idle: 'Choose a video to get started',
    selected: `Ready: ${videoFile?.name ?? ''}`,
    uploading: 'Uploading video...',
    analyzing: 'Analysing contents with AI...',
    done: `Done — found ${foundItems.length} item${foundItems.length !== 1 ? 's' : ''}`,
    error: errorMsg || 'Something went wrong',
  }

  const stageClass: Record<Stage, string> = {
    idle: '', selected: '',
    uploading: 'status-uploading', analyzing: 'status-analyzing',
    done: 'status-done', error: 'status-error',
  }

  const isBusy = stage === 'uploading' || stage === 'analyzing'

  return (
    <div className="container">
      <header>
        <button onClick={() => navigate('/')} className="back-btn">← Back</button>
        <h1>Upload Video</h1>
      </header>

      <main className="record-main">
        <div className={`record-status ${stageClass[stage]}`}>
          {isBusy && <span className="spinner" />}
          {stageLabel[stage]}
        </div>

        <div className="video-preview">
          <video ref={videoRef} controls />
        </div>

        <div className="upload-controls">
          <label className="large-btn secondary-btn">
            <span className="icon">{String.fromCodePoint(0x1F4C2)}</span>
            Choose Videos
            <input
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
          </label>

          {videoFile && stage !== 'done' && (
            <button
              className="large-btn primary-btn"
              onClick={handleUpload}
              disabled={isBusy}
            >
              {isBusy
                ? <><span className="spinner" /> Processing...</>
                : <>{String.fromCodePoint(0x1F4BE)} Save to Memory</>
              }
            </button>
          )}
        </div>

        {stage === 'done' && foundItems.length > 0 && (
          <div className="found-items">
            <p className="found-items-title">
              {String.fromCodePoint(0x1F4CB)} Items found in this video:
            </p>
            <ul className="found-items-list">
              {foundItems.map((item, i) => (
                <li key={i} className="found-item">
                  <span className="found-item-obj">{item.object}</span>
                  <span className="found-item-loc">
                    {item.location}{item.room ? ` · ${item.room}` : ''}{item.notes ? ` · ${item.notes}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {stage === 'done' && foundItems.length === 0 && (
          <div className="found-items">
            <p className="found-items-title status-error">
              No items identified. You can edit the index manually in My Videos.
            </p>
          </div>
        )}
      </main>
    </div>
  )
}
