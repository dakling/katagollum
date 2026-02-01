import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Trash Talk Go',
  description: 'A Go-playing bot with personality',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
