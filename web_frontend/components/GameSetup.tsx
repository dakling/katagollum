'use client'

import { useState } from 'react'

interface GameSetupProps {
  onStartGame: (config: {
    boardSize: number
    komi: number
    handicap: number
    userColor: string
    persona: string
  }) => Promise<void>
  isLoading: boolean
}

const GAME_TYPES = [
  { label: 'Default (Komi 6.5)', komi: 6.5, handicap: 0 },
  { label: 'No Komi', komi: 0, handicap: 0 },
  { label: '2 Stone Handicap', komi: 0.5, handicap: 2 },
  { label: '3 Stone Handicap', komi: 0.5, handicap: 3 },
  { label: '4 Stone Handicap', komi: 0.5, handicap: 4 },
  { label: '5 Stone Handicap', komi: 0.5, handicap: 5 },
  { label: '6 Stone Handicap', komi: 0.5, handicap: 6 },
  { label: '7 Stone Handicap', komi: 0.5, handicap: 7 },
  { label: '8 Stone Handicap', komi: 0.5, handicap: 8 },
  { label: '9 Stone Handicap', komi: 0.5, handicap: 9 },
]

export default function GameSetup({ onStartGame, isLoading }: GameSetupProps) {
  const [boardSize, setBoardSize] = useState(19)
  const [gameTypeIndex, setGameTypeIndex] = useState(0)
  const [userColor, setUserColor] = useState('B')
  const [persona, setPersona] = useState('arrogant')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const gameType = GAME_TYPES[gameTypeIndex]
    await onStartGame({ 
      boardSize, 
      komi: gameType.komi, 
      handicap: gameType.handicap,
      userColor, 
      persona 
    })
  }

  return (
    <div className="max-w-md mx-auto bg-gray-800 rounded-lg p-6">
      <h1 className="text-2xl font-bold mb-6 text-center">Trash Talk Go</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Board Size</label>
          <select
            value={boardSize}
            onChange={(e) => setBoardSize(Number(e.target.value))}
            className="w-full p-2 rounded bg-gray-700 border border-gray-600"
          >
            <option value={9}>9×9</option>
            <option value={13}>13×13</option>
            <option value={19}>19×19</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Game Type</label>
          <select
            value={gameTypeIndex}
            onChange={(e) => setGameTypeIndex(Number(e.target.value))}
            className="w-full p-2 rounded bg-gray-700 border border-gray-600"
          >
            {GAME_TYPES.map((type, index) => (
              <option key={index} value={index}>{type.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Your Color</label>
          <select
            value={userColor}
            onChange={(e) => setUserColor(e.target.value)}
            className="w-full p-2 rounded bg-gray-700 border border-gray-600"
          >
            <option value="B">Black</option>
            <option value="W">White</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Persona</label>
          <select
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            className="w-full p-2 rounded bg-gray-700 border border-gray-600"
          >
            <option value="arrogant">Arrogant</option>
            <option value="sarcastic">Sarcastic</option>
            <option value="encouraging">Encouraging</option>
            <option value="chill">Chill</option>
            <option value="competitive">Competitive</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={isLoading}
          className="w-full py-3 bg-blue-600 rounded font-bold hover:bg-blue-700 disabled:opacity-50"
        >
          {isLoading ? 'Starting...' : 'Start Game'}
        </button>
      </form>
    </div>
  )
}
