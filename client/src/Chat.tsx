import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function Chat() {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<{role: 'user' | 'assistant', text: string, videoName?: string}[]>([])
  const [status, setStatus] = useState('Ready')
  const [isRecording, setIsRecording] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' }) // Default to webm
        await sendAudio(audioBlob)
        
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop())
      }

      mediaRecorder.start()
      setIsRecording(true)
      setStatus('Listening...')
      
    } catch (err) {
      console.error("Error accessing microphone:", err)
      setStatus('Mic Error')
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
      setStatus('Processing...')
    }
  }

  const sendAudio = async (audioBlob: Blob) => {
    // Add temporary user message
    setMessages(prev => [...prev, { role: 'user', text: '🎤 (Audio Sent)' }])

    const formData = new FormData()
    formData.append('file', audioBlob, 'voice_query.webm')

    try {
      const response = await fetch(`${API_URL}/chat-audio`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Server error: ${response.status} ${errText}`);
      }

      const data = await response.json()
      console.log("Server response:", data); // Debug log

      // If backend returns {transcription, answer}, user UI should show transcription first?
      if (data.transcription) {
         setMessages(prev => {
            // Replace the last "🎤 (Audio Sent)" with real text
            const newMsgs = [...prev]
            if (newMsgs.length > 0 && newMsgs[newMsgs.length - 1].role === 'user') {
                newMsgs[newMsgs.length - 1].text = `🎤 "${data.transcription}"`
            }
            return newMsgs
         })
      }
      
      const textResponse = data.answer || data.response

      // Add assistant message (with optional video)
      setMessages(prev => [...prev, { role: 'assistant', text: textResponse, videoName: data.video_name || undefined }])
      setStatus('Ready')

      // Speak result
      speak(textResponse)

    } catch (error) {
      console.error('Error:', error)
      setStatus('Error')
      setMessages(prev => [...prev, { role: 'assistant', text: "Sorry, I couldn't reach the server." }])
    }
  }

  const speak = (text: string) => {
    if ('speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(text)
      window.speechSynthesis.speak(utterance)
    }
  }

  return (
    <div className="container chat-container">
      <header>
        <button className="back-btn" onClick={() => navigate('/')}>
          ← Back
        </button>
        <h1>Assistant</h1>
      </header>

      <main className="chat-main">
        <div className="messages-list">
            {messages.map((msg, idx) => (
            <div key={idx} className={`message ${msg.role === 'user' ? 'user-message' : 'bot-message'}`}>
                <span className="icon">{msg.role === 'user' ? '👤' : '🤖'}</span>
                <p style={{ margin: 0 }}>{msg.text}</p>
                {msg.videoName && (
                  <video
                    className="chat-video"
                    controls
                    src={`${API_URL}/videos/${encodeURIComponent(msg.videoName)}/stream`}
                  />
                )}
            </div>
            ))}
            {status === 'Processing...' && <p className="status-indicator">Thinking...</p>}
        </div>

        <div className="chat-controls">
            {!isRecording ? (
                <button className="large-btn primary-btn" onClick={startRecording}>
                    <span className="icon">🎤</span>
                    Tap to Speak
                </button>
            ) : (
                <button className="large-btn secondary-btn" style={{ backgroundColor: '#f44336' }} onClick={stopRecording}>
                    <span className="icon">⏹</span>
                    Stop & Send
                </button>
            )}
        </div>
      </main>
    </div>
  )
}

export default Chat