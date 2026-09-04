/**
 * Scoped inline styles for the talk client components. Standalone bundles
 * cannot use the in-repo CSS-module pipeline, so every rule lives here and is
 * installed (and removed) through one document-level `<style>` element.
 *
 * @module dsh-talk/client/styles
 */

/** One scoped stylesheet installation; returns its disposer. */
export function installTalkStyles(): () => void {
  const style = document.createElement('style')
  style.dataset['dshTalkStyles'] = '1'
  style.textContent = `
    [data-dsh-talk-mic] {
      display: inline-flex;
      justify-content: center;
      align-items: center;
      width: 28px;
      height: 28px;
      padding: 0;
      border: 0;
      border-radius: 50%;
      background: transparent;
      cursor: pointer;
      font: inherit;
      color: var(--dsw-alias-label-primary);
    }
    [data-dsh-talk-mic] svg {
      width: 24px;
      height: 24px;
    }
    [data-gerclaw-read-aloud] {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      padding: 0;
      border: 0 !important;
      border-radius: 50%;
      background: transparent;
      color: var(--dsw-alias-label-tertiary);
      cursor: pointer;
    }
    [data-gerclaw-read-aloud] svg {
      width: 24px;
      height: 24px;
    }
    [data-gerclaw-read-aloud]:hover:not(:disabled),
    [data-gerclaw-read-aloud]:focus-visible,
    [data-dsh-talk-mic]:hover,
    [data-dsh-talk-mic]:focus-visible {
      background: var(--dsw-alias-interactive-bg-hover);
      color: var(--dsw-alias-label-secondary);
      outline: none;
    }
    [data-gerclaw-voice-controls] {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    [data-gerclaw-voice-status] {
      max-width: 220px;
      overflow: hidden;
      color: var(--dsw-alias-label-secondary);
      font-size: 12px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    [data-composer-card]:has([data-gerclaw-recording-strip]) {
      position: relative;
      height: 52px;
      min-height: 52px;
      overflow: hidden;
    }
    [data-gerclaw-recording-strip] {
      position: absolute;
      z-index: 2;
      inset: 0;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      border-radius: inherit;
      background: var(--dsw-alias-bg-overlay);
    }
    [data-gerclaw-recording-strip] button {
      display: inline-flex;
      flex: none;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      padding: 0;
      border: 0;
      border-radius: 50%;
      cursor: pointer;
    }
    [data-gerclaw-recording-strip] button svg {
      width: 16px;
      height: 16px;
    }
    [data-gerclaw-recording-cancel],
    [data-gerclaw-recording-stop] {
      background: var(--dsw-alias-interactive-bg-hover);
      color: var(--dsw-alias-label-primary);
    }
    [data-gerclaw-recording-send] {
      background: var(--dsw-alias-label-primary);
      color: var(--dsw-alias-bg-overlay);
    }
    [data-gerclaw-recording-strip] button:disabled {
      opacity: .45;
      cursor: wait;
    }
    [data-gerclaw-recording-wave] {
      position: relative;
      flex: 1;
      height: 20px;
      background: radial-gradient(circle, var(--dsw-alias-label-caption) 1px, transparent 1.5px) center / 6px 4px repeat-x;
    }
    [data-gerclaw-recording-wave]::after {
      position: absolute;
      top: 1px;
      left: 78%;
      width: 2px;
      height: 18px;
      border-radius: 2px;
      background: var(--dsw-alias-label-secondary);
      content: '';
      animation: gerclaw-recording-pulse 1.2s ease-in-out infinite;
    }
    @keyframes gerclaw-recording-pulse {
      50% { transform: scaleY(.55); opacity: .65; }
    }
    [data-dsh-talk-settings] {
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: 560px;
    }
    [data-dsh-talk-settings] label {
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 0.85em;
    }
    [data-dsh-talk-settings] select,
    [data-dsh-talk-settings] input[type='text'] {
      padding: 4px 6px;
      font: inherit;
    }
    [data-dsh-talk-settings] .row {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.9em;
    }
    [data-dsh-talk-settings] .note {
      font-size: 0.8em;
      opacity: 0.75;
    }
    @media (prefers-reduced-motion: reduce) {
      [data-gerclaw-recording-wave]::after { animation: none; }
    }
  `
  document.head.appendChild(style)
  return () => {
    style.remove()
  }
}
