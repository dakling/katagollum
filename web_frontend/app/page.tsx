'use client'

import { useState, useEffect, useCallback } from 'react'
import GameSetup from '@/components/GameSetup'
import GoBoard from '@/components/GoBoard'
import Chat from '@/components/Chat'
import { createGame, getGameBoard, submitMove, getChatMessages, sendChatMessage, getFirstMove, BoardState, ChatMsg, Game, getKataGoBoardState, KataGoBoardState } from '@/lib/api'

export default function Home() {
  const [game, setGame] = useState<Game | null>(null)
  const [boardState, setBoardState] = useState<BoardState | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isThinking, setIsThinking] = useState(false)
  const [previewCoord, setPreviewCoord] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pendingMove, setPendingMove] = useState<{
    row: number
    col: number
    color: string
  } | null>(null)
  const [lastMoveCoord, setLastMoveCoord] = useState<string | null>(null)

  // Helper to parse coordinate to row/col
  const parseCoordinate = (coord: string, boardSize: number): { row: number; col: number } => {
    const letter = coord[0].toUpperCase()
    const number = parseInt(coord.slice(1))
    
    let col = letter.charCodeAt(0) - 65 // A=0, B=1, etc.
    if (col >= 8) col-- // Skip 'I'
    
    const row = boardSize - number
    
    return { row, col }
  }

  const startGame = useCallback(async (config: {
    boardSize: number
    komi: number
    handicap: number
    userColor: string
    persona: string
  }) => {
    setIsSubmitting(true)
    setError(null)
    try {
      console.log('[PAGE] Creating game with config:', config)
      const newGame = await createGame(config.boardSize, config.komi, config.handicap, config.userColor, config.persona)
      console.log('[PAGE] Game created:', newGame)
      setGame(newGame)

      // Check if LLM should make the first move
      const llmShouldMoveFirst = (config.handicap === 0 && config.userColor === 'W') || 
                                  (config.handicap > 0 && config.userColor === 'B')
      
      if (llmShouldMoveFirst) {
        console.log('[PAGE] LLM should make first move, showing waiting indicator')
        // Show bouncing dots while waiting
        setMessages([
          { 
            id: Date.now(), 
            role: 'assistant', 
            content: '...', 
            created_at: new Date().toISOString() 
          },
        ])
        setIsThinking(true)
        
        try {
          const firstMoveResult = await getFirstMove(newGame.id)
          console.log('[PAGE] First move result:', firstMoveResult)
          
          if (firstMoveResult.move) {
            // Update messages with LLM's greeting
            setMessages([
              {
                id: Date.now(),
                role: 'assistant',
                content: firstMoveResult.message || `I play ${firstMoveResult.move}`,
                created_at: new Date().toISOString()
              },
            ])

            // Update board with the first move
            if (firstMoveResult.board_state) {
              setBoardState(firstMoveResult.board_state)
            }

            // Track the last move for the marker
            setLastMoveCoord(firstMoveResult.move)
          } else {
            // No first move needed or error
            setMessages([])
          }
        } catch (err) {
          console.error('[PAGE] Error getting first move:', err)
          setError('Failed to get first move from KataGo')
          setMessages([])
        } finally {
          setIsThinking(false)
        }
      } else {
        console.log('[PAGE] User should make first move')
        // Fetch initial empty board
        console.log('[PAGE] Fetching initial board from database')
        const board = await getGameBoard(newGame.id)
        console.log('[PAGE] Got initial board:', board)
        setBoardState(board)

        const msgs = await getChatMessages(newGame.id)
        setMessages(msgs)
      }
    } catch (err) {
      setError('Failed to start game. Make sure the backend server is running.')
      console.error(err)
    } finally {
      setIsSubmitting(false)
    }
  }, [])

  const handleMoveSubmit = async (coordinate: string) => {
    if (!game || isSubmitting) return
    setPreviewCoord(null)
    setError(null)

    // Set pending move for ghost stone preview
    const { row, col } = parseCoordinate(coordinate, game.board_size)
    setPendingMove({ row, col, color: game.user_color })

    const userMsgId = Date.now()

    setMessages(prev => [
      ...prev,
      { id: userMsgId, role: 'user', content: `My move: ${coordinate}`, created_at: new Date().toISOString() },
    ])

    setIsSubmitting(true)
    setIsThinking(true)

    try {
      const result = await submitMove(game.id, coordinate)

      setMessages(prev => [
        ...prev.filter(m => m.id !== userMsgId),
        { id: userMsgId, role: 'user', content: `My move: ${coordinate}`, created_at: new Date().toISOString() },
        { id: Date.now() + 1, role: 'assistant', content: result.bot_response, created_at: new Date().toISOString() },
      ])

      // Track the last move (AI's response move) for the marker
      console.log('[PAGE] result.ai_move:', result.ai_move, 'type:', typeof result.ai_move)
      if (result.ai_move) {
        setLastMoveCoord(result.ai_move)
      } else {
        // If no AI move (e.g., pass or game over), show user's last move
        setLastMoveCoord(coordinate)
      }

      console.log('[PAGE] Fetching board state from KataGo...')
      const kataGoBoard = await getKataGoBoardState()
      console.log('[PAGE] Got KataGo board:', JSON.stringify(kataGoBoard))
      console.log('[PAGE] KataGo board valid?', !!kataGoBoard && kataGoBoard.board.length > 0)

      if (kataGoBoard && kataGoBoard.board.length > 0) {
        console.log('[PAGE] Updating board with KataGo state, board rows:', kataGoBoard.board.length)
        console.log('[PAGE] First row sample:', kataGoBoard.board[0].join(''))
        console.log('[PAGE] Board contains stones:', kataGoBoard.board.some(row => row.some(cell => cell !== '.')))
        setBoardState(prev => {
          const newState = {
            board_size: kataGoBoard.board_size,
            komi: prev?.komi || game.komi,
            user_color: prev?.user_color || game.user_color,
            ai_color: prev?.ai_color || game.ai_color,
            game_over: prev?.game_over || game.game_over,
            board: kataGoBoard.board,
            moves: prev?.moves || [],
          }
          console.log('[PAGE] Set board state to:', newState)
          return newState
        })
      } else {
        console.log('[PAGE] KataGo board not available, falling back to database')
        const board = await getGameBoard(game.id)
        console.log('[PAGE] Got DB board, board rows:', board.board.length)
        setBoardState(board)
      }
    } catch (err) {
      setError('Failed to submit move')
      console.error(err)
      setMessages(prev => prev.filter(m => m.id !== userMsgId))
    } finally {
      setIsSubmitting(false)
      setIsThinking(false)
      setPendingMove(null) // Clear ghost stone preview
    }
  }

  const handleHoverChange = (coord: string | null) => {
    setPreviewCoord(coord)
  }

  const handleChatMessage = async (content: string) => {
    if (!game || isSubmitting || isThinking) return
    setError(null)

    const userMsgId = Date.now()
    setMessages(prev => [
      ...prev,
      {
        id: userMsgId,
        role: 'user',
        content: content,
        created_at: new Date().toISOString()
      },
    ])
    setIsThinking(true)

    try {
      const result = await sendChatMessage(game.id, content)
      const botContent = typeof result.bot_message?.content === 'string'
        ? result.bot_message.content
        : String(result.bot_message || "...")

      setMessages(prev => [
        ...prev.filter(m => m.id !== userMsgId),
        {
          id: userMsgId,
          role: 'user',
          content: content,
          created_at: new Date().toISOString()
        },
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: botContent,
          created_at: new Date().toISOString()
        },
      ])

      console.log('[PAGE] Fetching board state from KataGo after chat...')
      const kataGoBoard = await getKataGoBoardState()
      console.log('[PAGE] Got KataGo board:', JSON.stringify(kataGoBoard))
      console.log('[PAGE] KataGo board valid?', !!kataGoBoard && kataGoBoard.board.length > 0)

      if (kataGoBoard && kataGoBoard.board.length > 0) {
        console.log('[PAGE] Updating board with KataGo state, board rows:', kataGoBoard.board.length)
        console.log('[PAGE] First row sample:', kataGoBoard.board[0].join(''))
        console.log('[PAGE] Board contains stones:', kataGoBoard.board.some(row => row.some(cell => cell !== '.')))
        setBoardState(prev => {
          const newState = {
            board_size: kataGoBoard.board_size,
            komi: prev?.komi || game.komi,
            user_color: prev?.user_color || game.user_color,
            ai_color: prev?.ai_color || game.ai_color,
            game_over: prev?.game_over || game.game_over,
            board: kataGoBoard.board,
            moves: prev?.moves || [],
          }
          console.log('[PAGE] Set board state to:', newState)
          return newState
        })
      } else {
        console.log('[PAGE] KataGo board not available, falling back to database')
        const board = await getGameBoard(game.id)
        console.log('[PAGE] Got DB board, board rows:', board.board.length)
        setBoardState(board)
      }
    } catch (err) {
      console.error('Chat error:', err)
      setError('Failed to send message')
      setMessages(prev => prev.filter(m => m.id !== userMsgId))
    } finally {
      setIsThinking(false)
    }
  }

  if (!game) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <GameSetup onStartGame={startGame} isLoading={isSubmitting} />
        {error && (
          <div className="fixed bottom-4 bg-red-600 text-white px-4 py-2 rounded">
            {error}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Trash Talk Go</h1>
          <div className="text-sm text-gray-400">
            {boardState?.board_size}×{boardState?.board_size} • Komi: {boardState?.komi} • {boardState?.user_color === 'B' ? 'You: Black' : 'You: White'}
          </div>
        </div>

        {error && (
          <div className="mb-4 bg-red-600 text-white px-4 py-2 rounded">
            {error}
          </div>
        )}

        <div className="flex flex-col lg:flex-row gap-6">
          <div className="flex-shrink-0">
            <GoBoard
              boardState={boardState}
              onMoveSubmit={handleMoveSubmit}
              isSubmitting={isSubmitting}
              userColor={game.user_color}
              onHoverChange={handleHoverChange}
              pendingMove={pendingMove}
              lastMoveCoord={lastMoveCoord}
            />
          </div>
          <div className="flex-grow max-w-md">
            <Chat
              messages={messages}
              onSendMessage={handleChatMessage}
              isSubmitting={isSubmitting}
              isThinking={isThinking}
              previewCoord={previewCoord}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
