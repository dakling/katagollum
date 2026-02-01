'use client'

import { useState, useEffect, useRef } from 'react'
import { ChatMsg, sendChatMessage } from '@/lib/api'

interface ChatProps {
  messages: ChatMsg[]
  onSendMessage: (content: string) => Promise<void>
  isSubmitting: boolean
  isThinking: boolean
  previewCoord: string | null
}

export default function Chat({ messages, onSendMessage, isSubmitting, isThinking, previewCoord }: ChatProps) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isThinking, previewCoord])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isSubmitting || isThinking) return
    const messageToSend = input
    setInput('')
    await onSendMessage(messageToSend)
  }

  const formatMessage = (content: string) => {
    const lines = content.split('\n')
    return lines.map((line, i) => (
      <span key={i}>
        {line}
        {i < lines.length - 1 && <br />}
      </span>
    ))
  }

  return (
    <div className="chat-container bg-gray-800 rounded-lg h-[780px] flex flex-col">
      <div className="chat-messages flex-grow overflow-y-auto p-3 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`chat-message ${msg.role === 'user' ? 'user' : 'assistant'} text-sm`}
          >
            <span className="font-bold text-xs opacity-70 mb-1 block">
              {msg.role === 'user' ? 'You' : 'Bot'}
            </span>
            {formatMessage(msg.content)}
          </div>
        ))}
        {previewCoord && !isThinking && (
          <div className="chat-message user text-sm opacity-50">
            <span className="font-bold text-xs opacity-70 mb-1 block">
              You
            </span>
            <span className="italic">My move: {previewCoord}</span>
          </div>
        )}
        {isThinking && (
          <div className="chat-message assistant text-sm">
            <span className="font-bold text-xs opacity-70 mb-1 block">
              Bot
            </span>
            <div className="flex gap-1 items-center">
              <span className="animate-bounce">.</span>
              <span className="animate-bounce" style={{ animationDelay: '0.2s' }}>.</span>
              <span className="animate-bounce" style={{ animationDelay: '0.4s' }}>.</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={handleSubmit} className="chat-input p-3 border-t border-gray-700 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Enter your move (e.g., Q16) or chat..."
          disabled={isSubmitting || isThinking}
          className="flex-grow text-sm px-3 py-2 rounded bg-gray-700 text-white border border-gray-600 focus:outline-none focus:border-blue-500"
        />
        <button
          type="submit"
          disabled={isSubmitting || isThinking || !input.trim()}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </form>
    </div>
  )
}
