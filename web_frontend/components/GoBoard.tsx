'use client'

import { useState } from 'react'
import { BoardState } from '@/lib/api'

interface GoBoardProps {
  boardState: BoardState | null
  onMoveSubmit: (coordinate: string) => Promise<void>
  isSubmitting: boolean
  userColor: string
  onHoverChange?: (coord: string | null) => void
  pendingMove?: {
    row: number
    col: number
    color: string
  } | null
  lastMoveCoord?: string | null
}

export default function GoBoard({ boardState, onMoveSubmit, isSubmitting, userColor, onHoverChange, pendingMove, lastMoveCoord }: GoBoardProps) {
  const [hoverCoord, setHoverCoord] = useState<string | null>(null)

  if (!boardState) {
    return (
      <div className="flex items-center justify-center bg-amber-200 rounded-lg" style={{ width: '800px', height: '860px' }}>
        <p className="text-gray-600">Loading board...</p>
      </div>
    )
  }

  const board_size = boardState.board_size
  const cellSize = 40
  const padding = 30
  const boardPixelSize = (board_size - 1) * cellSize
  const labelSize = 24

  const getCoordinate = (row: number, col: number): string => {
    let letter = String.fromCharCode(65 + col)
    if (col >= 8) letter = String.fromCharCode(66 + col)
    const number = board_size - row
    return letter + number
  }

  const parseCoordinate = (coord: string): { row: number; col: number } | null => {
    if (!coord || coord.length < 2) return null
    const letter = coord[0].toUpperCase()
    const number = parseInt(coord.slice(1), 10)
    if (isNaN(number)) return null

    const charCode = letter.charCodeAt(0)
    // Letters skip 'I', so A-H map to 0-7, J-T map to 8-18
    const col = charCode > 73 ? charCode - 66 : charCode - 65  // 73 is 'I'
    const row = board_size - number

    if (row < 0 || row >= board_size || col < 0 || col >= board_size) return null
    return { row, col }
  }

  // Parse the last move coordinate for the marker
  const lastMovePos = lastMoveCoord ? parseCoordinate(lastMoveCoord) : null
  console.log('[GOBOARD] lastMoveCoord:', lastMoveCoord, '-> lastMovePos:', lastMovePos)

  const handleCellClick = async (row: number, col: number) => {
    if (isSubmitting) return
    const coord = getCoordinate(row, col)
    await onMoveSubmit(coord)
  }

  const handleCellHover = (row: number, col: number) => {
    const coord = getCoordinate(row, col)
    setHoverCoord(coord)
    onHoverChange?.(coord)
  }

  const handleCellLeave = () => {
    setHoverCoord(null)
    onHoverChange?.(null)
  }

  const renderStarPoints = (size: number): boolean[][] => {
    const stars: boolean[][] = Array(size).fill(null).map(() => Array(size).fill(false))
    if (size === 19) {
      ;[3, 9, 15].forEach(r => {
        ;[3, 9, 15].forEach(c => {
          stars[r][c] = true
        })
      })
    } else if (size === 13) {
      ;[3, 9].forEach(r => {
        ;[3, 9].forEach(c => {
          stars[r][c] = true
        })
      })
    } else if (size === 9) {
      // 9x9 has 5 star points: 4 corners and center
      const positions = [2, 6]
      positions.forEach(r => {
        positions.forEach(c => {
          stars[r][c] = true
        })
      })
      stars[4][4] = true // center
    }
    return stars
  }

  const starPoints = renderStarPoints(board_size)

  const colLabels = []
  for (let i = 0; i < board_size; i++) {
    let letter = String.fromCharCode(65 + i)
    if (i >= 8) letter = String.fromCharCode(66 + i)
    colLabels.push(letter)
  }

  const rowLabels = []
  for (let i = board_size; i >= 1; i--) {
    rowLabels.push(i.toString())
  }

  const verticalLines = []
  for (let i = 0; i < board_size; i++) {
    verticalLines.push(
      <line
        key={`v-${i}`}
        x1={padding + i * cellSize}
        y1={padding}
        x2={padding + i * cellSize}
        y2={padding + boardPixelSize}
        stroke="#5c3d2e"
        strokeWidth="1.5"
      />
    )
  }

  const horizontalLines = []
  for (let i = 0; i < board_size; i++) {
    horizontalLines.push(
      <line
        key={`h-${i}`}
        x1={padding}
        y1={padding + i * cellSize}
        x2={padding + boardPixelSize}
        y2={padding + i * cellSize}
        stroke="#5c3d2e"
        strokeWidth="1.5"
      />
    )
  }

  const starPointElements = []
  for (let r = 0; r < board_size; r++) {
    for (let c = 0; c < board_size; c++) {
      if (starPoints[r][c]) {
        starPointElements.push(
          <circle
            key={`star-${r}-${c}`}
            cx={padding + c * cellSize}
            cy={padding + r * cellSize}
            r="6"
            fill="#5c3d2e"
          />
        )
      }
    }
  }

  const displayBoard = boardState.board

  console.log('[GOBOARD] Rendering board, board size:', board_size)
  console.log('[GOBOARD] displayBoard rows:', displayBoard.length)
  if (displayBoard.length > 0) {
    console.log('[GOBOARD] First row:', displayBoard[0].join(''))
    const hasStones = displayBoard.some(row => row.some(cell => cell !== '.'))
    console.log('[GOBOARD] Board has stones:', hasStones)
    console.log('[GOBOARD] Full board (first 5 rows):')
    displayBoard.slice(0, 5).forEach((row, idx) => {
      console.log(`[GOBOARD]   Row ${idx}:`, row.join(''))
    })
  }

  const boardWidth = padding + boardPixelSize + padding
  const boardHeight = padding + boardPixelSize + padding

  const totalWidth = labelSize + boardWidth
  const totalHeight = labelSize + boardHeight

  return (
    <div 
      className="relative"
      style={{ 
        width: `${totalWidth}px`,
        height: `${totalHeight}px`,
      }}
    >
      <svg
        width={boardWidth}
        height={boardHeight}
        style={{ position: 'absolute', top: 0, left: labelSize }}
      >
        <rect x={padding} y={padding} width={boardPixelSize} height={boardPixelSize} fill="#d4a056" />
        {verticalLines}
        {horizontalLines}
        {starPointElements}
      </svg>

      <div
        className="absolute cursor-pointer"
        style={{
          left: `${labelSize + padding}px`,
          top: `${padding}px`,
          width: `${boardPixelSize}px`,
          height: `${boardPixelSize}px`,
        }}
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          const x = e.clientX - rect.left
          const y = e.clientY - rect.top
          const col = Math.round(x / cellSize)
          const row = Math.round(y / cellSize)
          if (row >= 0 && row < board_size && col >= 0 && col < board_size) {
            handleCellClick(row, col)
          }
        }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          const x = e.clientX - rect.left
          const y = e.clientY - rect.top
          const col = Math.round(x / cellSize)
          const row = Math.round(y / cellSize)
          if (row >= 0 && row < board_size && col >= 0 && col < board_size) {
            handleCellHover(row, col)
          } else {
            handleCellLeave()
          }
        }}
        onMouseLeave={() => handleCellLeave()}
      >
        {displayBoard.map((row, rowIndex) =>
          row.map((cell, colIndex) => {
            const coord = getCoordinate(rowIndex, colIndex)
            const isHovered = hoverCoord === coord

            return (
              <div
                key={`${rowIndex}-${colIndex}`}
                className="absolute flex items-center justify-center"
                style={{
                  left: `${colIndex * cellSize - 16}px`,
                  top: `${rowIndex * cellSize - 16}px`,
                  width: '32px',
                  height: '32px',
                }}
              >
                {cell !== '.' && (
                  <div
                    className="w-8 h-8 rounded-full shadow-lg relative"
                    style={{
                      background: cell === 'B'
                        ? 'radial-gradient(circle at 30% 30%, #444, #000)'
                        : 'radial-gradient(circle at 30% 30%, #fff, #ccc)',
                    }}
                  >
                    {/* Last move marker - contrasting circle */}
                    {lastMovePos && lastMovePos.row === rowIndex && lastMovePos.col === colIndex && (
                      <div
                        className="absolute inset-0 flex items-center justify-center"
                      >
                        <div
                          className="w-4 h-4 rounded-full border-2"
                          style={{
                            borderColor: cell === 'B' ? '#fff' : '#000',
                            backgroundColor: 'transparent',
                          }}
                        />
                      </div>
                    )}
                  </div>
                )}
                {isHovered && cell === '.' && (
                  <div
                    className="w-6 h-6 rounded-full opacity-40"
                    style={{
                      backgroundColor: userColor === 'B' ? '#000' : '#fff',
                    }}
                  />
                )}
              </div>
            )
          })
        )}
        
        {/* Ghost stone preview for pending move */}
        {pendingMove && isSubmitting && (
          <div
            className="absolute flex items-center justify-center"
            style={{
              left: `${pendingMove.col * cellSize - 16}px`,
              top: `${pendingMove.row * cellSize - 16}px`,
              width: '32px',
              height: '32px',
              opacity: 0.6,
              transition: 'opacity 0.2s ease-in-out',
            }}
          >
            <div
              className="w-8 h-8 rounded-full shadow-lg"
              style={{
                background: pendingMove.color === 'B'
                  ? 'radial-gradient(circle at 30% 30%, #444, #000)'
                  : 'radial-gradient(circle at 30% 30%, #fff, #ccc)',
              }}
            />
            {/* Waiting indicator overlay */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex gap-0.5">
                <span className="animate-bounce text-xs font-bold" style={{ color: pendingMove.color === 'B' ? '#fff' : '#000' }}>.</span>
                <span className="animate-bounce text-xs font-bold" style={{ animationDelay: '0.2s', color: pendingMove.color === 'B' ? '#fff' : '#000' }}>.</span>
                <span className="animate-bounce text-xs font-bold" style={{ animationDelay: '0.4s', color: pendingMove.color === 'B' ? '#fff' : '#000' }}>.</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {colLabels.map((label, i) => (
        <div
          key={`col-top-${i}`}
          className="absolute flex items-end justify-center text-sm text-gray-700 font-bold"
          style={{
            left: `${labelSize + padding + i * cellSize - labelSize / 2}px`,
            top: '0px',
            width: `${labelSize}px`,
            height: `${labelSize}px`,
          }}
        >
          {label}
        </div>
      ))}

      {colLabels.map((label, i) => (
        <div
          key={`col-bottom-${i}`}
          className="absolute flex items-start justify-center text-sm text-gray-700 font-bold"
          style={{
            left: `${labelSize + padding + i * cellSize - labelSize / 2}px`,
            top: `${padding + boardPixelSize}px`,
            width: `${labelSize}px`,
            height: `${labelSize}px`,
          }}
        >
          {label}
        </div>
      ))}

      {rowLabels.map((label, i) => (
        <div
          key={`row-left-${i}`}
          className="absolute flex items-center justify-end text-sm text-gray-700 font-bold pr-1"
          style={{
            left: `${labelSize / 2}px`,
            top: `${padding + i * cellSize - labelSize / 2}px`,
            width: `${labelSize}px`,
            height: `${labelSize}px`,
          }}
        >
          {label}
        </div>
      ))}

      {rowLabels.map((label, i) => (
        <div
          key={`row-right-${i}`}
          className="absolute flex items-center justify-start text-sm text-gray-700 font-bold pl-1"
          style={{
            left: `${labelSize + padding + boardPixelSize}px`,
            top: `${padding + i * cellSize - labelSize / 2}px`,
            width: `${labelSize}px`,
            height: `${labelSize}px`,
          }}
        >
          {label}
        </div>
      ))}
    </div>
  )
}
