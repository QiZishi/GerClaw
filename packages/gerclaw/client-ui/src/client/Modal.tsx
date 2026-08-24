import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { CloseIcon } from './icons.tsx'

export function Modal({ title, onClose, children }: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const prior = document.activeElement as HTMLElement | null
    panel.current?.focus()
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      prior?.focus()
    }
  }, [onClose])
  return createPortal(
    <div data-gerclaw-modal-backdrop role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <div ref={panel} data-gerclaw-modal role="dialog" aria-modal="true" aria-labelledby="gerclaw-modal-title" tabIndex={-1}>
        <header>
          <h2 id="gerclaw-modal-title">{title}</h2>
          <button type="button" onClick={onClose} aria-label="关闭">
            <CloseIcon />
          </button>
        </header>
        <div data-gerclaw-modal-body>{children}</div>
      </div>
    </div>,
    document.body,
  )
}
