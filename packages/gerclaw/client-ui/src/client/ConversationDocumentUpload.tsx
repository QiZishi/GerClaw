import { useRef, useState } from 'react'
import { Tooltip } from '@deepseek-ai/dsh-client-ui-primitives'
import type { InjectFace, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import { UploadIcon } from './icons.tsx'

interface UploadedDocument {
  documentId: string
  name: string
  parseStatus: string
}

export interface ConversationDocumentUploadInjected {
  sessionId: string
}

type ConversationDocumentUploadProps = PropsRuntime<'conversation.input.left'>
  & InjectFace<ConversationDocumentUploadInjected>

async function fileBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  const chunkSize = 32 * 1024
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize))
  }
  return btoa(binary)
}

async function uploadDocument(
  file: File,
  sessionId: string,
): Promise<UploadedDocument> {
  const response = await fetch('/gerclaw/api/documents', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-gerclaw-session-id': sessionId,
    },
    body: JSON.stringify({ name: file.name, data: await fileBase64(file) }),
  })
  const body = await response.json() as UploadedDocument & { error?: string }
  if (!response.ok) throw new Error(body.error ?? `资料上传失败（${response.status}）`)
  if (body.parseStatus !== 'ready') throw new Error('资料解析尚未完成')
  return body
}

/** Native composer control for account-scoped prescription source documents. */
export function ConversationDocumentUpload({
  sessionId,
  input,
  inputActions,
}: ConversationDocumentUploadProps) {
  const picker = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [status, setStatus] = useState('')
  const select = (): void => { picker.current?.click() }
  return (
    <div data-gerclaw-composer-document>
      <input
        ref={picker}
        type="file"
        accept=".pdf,.docx,.md,.txt,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        multiple
        hidden
        onChange={(event) => {
          const files = [...(event.target.files ?? [])]
          event.target.value = ''
          if (files.length === 0) return
          if (files.length > 10) {
            setStatus('一次最多上传 10 份资料')
            return
          }
          setUploading(true)
          setStatus(`正在解析 ${files.length} 份资料…`)
          void Promise.all(files.map(file => uploadDocument(file, sessionId)))
            .then((documents) => {
              const markers = documents.map(
                document => `已上传健康资料《${document.name}》（资料编号：${document.documentId}）`,
              ).join('\n')
              inputActions.setDraft([input.draft.trim(), markers].filter(Boolean).join('\n'))
              setStatus(`已解析 ${documents.length} 份资料，请补充说明后发送`)
              window.setTimeout(() => {
                document.querySelector<HTMLTextAreaElement>('[data-composer-card] textarea')?.focus()
              }, 0)
            })
            .catch((error: unknown) => {
              setStatus(error instanceof Error ? error.message : '资料上传失败')
            })
            .finally(() => { setUploading(false) })
        }}
      />
      <Tooltip label="上传健康资料（PDF、Word、Markdown 或文本）" side="top" delayMs={350}>
        <button
          type="button"
          aria-label="上传健康资料"
          disabled={uploading || input.phase !== 'plain'}
          onClick={select}
        >
          <UploadIcon size={16} />
        </button>
      </Tooltip>
      {status && <span data-gerclaw-upload-status role="status">{status}</span>}
    </div>
  )
}
