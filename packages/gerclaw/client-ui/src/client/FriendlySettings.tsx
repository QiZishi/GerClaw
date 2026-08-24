import { useCallback, useEffect, useRef, useState } from 'react'
import { Tooltip } from '@deepseek-ai/dsh-client-ui-primitives'
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import { SettingsIcon } from './icons.tsx'
import { Modal } from './Modal.tsx'

interface AccountInfo {
  username?: string
  audience?: 'doctor' | 'patient'
  guest?: boolean
}

export function FriendlySettings({ wide }: PropsRuntime<'sidebar.settings'>) {
  const [open, setOpen] = useState(false)
  const [account, setAccount] = useState<AccountInfo>({})
  const [voice, setVoice] = useState(() => localStorage.getItem('gerclaw.voice') ?? 'Cherry')
  const [credentialMessage, setCredentialMessage] = useState('')
  const [recoveryCode, setRecoveryCode] = useState('')
  const credentialForm = useRef<HTMLFormElement>(null)
  const close = useCallback(() => { setOpen(false) }, [])
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    void fetch('/auth/me', { signal: controller.signal })
      .then(async response => response.ok ? await response.json() as AccountInfo : {})
      .then(setAccount)
      .catch(() => {})
    return () => { controller.abort() }
  }, [open])
  const trigger = (
    <button
      type="button"
      data-gerclaw-settings-trigger
      data-wide={String(wide)}
      aria-label="设置"
      onClick={() => { setOpen(true) }}
    >
      <SettingsIcon size={18} />
      {wide && <span>设置</span>}
    </button>
  )
  return (
    <>
      <Tooltip label="设置" side="right" delayMs={350}>{trigger}</Tooltip>
      {open && (
        <Modal title="设置" onClose={close}>
          <div data-gerclaw-setting-row>
            <label>当前账号</label>
            <span>{account.guest ? '游客' : (account.username ?? '已登录账号')} · {account.audience === 'doctor' ? '医生称呼' : '患者称呼'}</span>
          </div>
          <div data-gerclaw-setting-row>
            <label htmlFor="gerclaw-voice">语音音色</label>
            <select id="gerclaw-voice" value={voice} onChange={(event) => {
              const next = event.target.value
              setVoice(next)
              localStorage.setItem('gerclaw.voice', next)
            }}>
              <option value="Cherry">Cherry（温和女声）</option>
              <option value="Serena">Serena（沉稳女声）</option>
              <option value="Ethan">Ethan（自然男声）</option>
            </select>
          </div>
          <div data-gerclaw-setting-row>
            <label>模型</label>
            <span>可在对话输入框旁的“模型”入口切换已有模型。</span>
          </div>
          {!account.guest && (
            <form ref={credentialForm} data-gerclaw-credential-form onSubmit={(event) => {
              event.preventDefault()
              setCredentialMessage('正在更新…')
              setRecoveryCode('')
              const form = new FormData(event.currentTarget)
              void fetch('/auth/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  currentPassword: form.get('currentPassword'),
                  password: form.get('password'),
                }),
              }).then(async (response) => {
                const value = await response.json() as { error?: string; recoveryCode?: string }
                if (!response.ok) throw new Error(value.error ?? '更新失败')
                setRecoveryCode(value.recoveryCode ?? '')
                setCredentialMessage('密码已更新。请立即保存新的一次性恢复码。')
                credentialForm.current?.reset()
              }).catch((error: unknown) => {
                setCredentialMessage(error instanceof Error ? error.message : '更新失败')
              })
            }}>
              <strong>账号安全</strong>
              <label>当前密码<input name="currentPassword" type="password" autoComplete="current-password" required /></label>
              <label>新密码<input name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} required /></label>
              <button type="submit">更新密码并生成新恢复码</button>
              {credentialMessage && <p role="status">{credentialMessage}</p>}
              {recoveryCode && <output aria-label="新的一次性恢复码">{recoveryCode}</output>}
            </form>
          )}
          <div data-gerclaw-setting-row>
            <button type="button" onClick={() => {
              void fetch('/auth/logout', { method: 'POST' }).finally(() => { window.location.assign('/') })
            }}>退出当前账号</button>
          </div>
        </Modal>
      )}
    </>
  )
}
