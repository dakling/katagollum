const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'
const MCP_BASE = process.env.NEXT_PUBLIC_MCP_URL || 'http://localhost:3001'

export interface Game {
  id: number
  board_size: number
  komi: number
  handicap: number
  user_color: string
  ai_color: string
  game_over: boolean
  persona: string
  created_at: string
}

export interface Move {
  id: number
  color: string
  coordinate: string
  move_number: number
}

export interface BoardState {
  board_size: number
  komi: number
  user_color: string
  ai_color: string
  game_over: boolean
  board: string[][]
  moves: Move[]
}

export interface ChatMsg {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export async function createGame(
  boardSize: number = 19,
  komi: number = 7.5,
  handicap: number = 0,
  userColor: string = 'B',
  persona: string = 'arrogant'
): Promise<Game> {
  const res = await fetch(`${API_BASE}/initialize/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ board_size: boardSize, komi, handicap, user_color: userColor, persona }),
  })
  return res.json()
}

export async function getGameBoard(gameId: number): Promise<BoardState> {
  const res = await fetch(`${API_BASE}/games/${gameId}/board/`)
  return res.json()
}

export async function submitMove(gameId: number, coordinate: string): Promise<{
  game: Game
  user_move: string
  ai_move: string
  score_delta: number
  bot_response: string
}> {
  const res = await fetch(`${API_BASE}/games/${gameId}/submit_move/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ coordinate }),
  })
  return res.json()
}

export async function getChatMessages(gameId: number): Promise<ChatMsg[]> {
  const res = await fetch(`${API_BASE}/chat/?game_id=${gameId}`)
  return res.json()
}

export async function sendChatMessage(
  gameId: number,
  content: string,
  role: string = 'user'
): Promise<{ user_message: ChatMsg; bot_message: ChatMsg }> {
  const res = await fetch(`${API_BASE}/chat/send_message/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game_id: gameId, content, role }),
  })
  if (!res.ok) {
    const error = await res.text()
    throw new Error(`API error: ${error}`)
  }
  return res.json()
}

export interface KataGoBoardState {
  board: string[][]
  board_size: number
}

export async function getKataGoBoardState(): Promise<KataGoBoardState | null> {
  try {
    const url = `${MCP_BASE}/board_state`
    console.log('[API] Fetching board state from:', url)
    const res = await fetch(url, {
      signal: AbortSignal.timeout(10000),
    })
    if (!res.ok) {
      console.error('[API] Failed to fetch board state from KataGo, status:', res.status)
      return null
    }
    const data = await res.json()
    console.log('[API] KataGo board state response:', data)

    if (!data.result) {
      console.warn('[API] No result field in KataGo response')
      return null
    }

    const board = data.result.board as string[][]
    if (!board || !Array.isArray(board) || board.length === 0) {
      console.warn('[API] Invalid board in KataGo response')
      return null
    }

    console.log('[API] Successfully parsed board with', board.length, 'rows')
    return {
      board: board,
      board_size: data.result.board_size || board.length,
    }
  } catch (err) {
    console.error('[API] Error fetching board state from KataGo:', err)
    return null
  }
}

export async function getFirstMove(gameId: number): Promise<{
  move: string | null
  color: string | null
  message: string | null
  board_state: BoardState
}> {
  const res = await fetch(`${API_BASE}/games/${gameId}/first_move/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return res.json()
}
