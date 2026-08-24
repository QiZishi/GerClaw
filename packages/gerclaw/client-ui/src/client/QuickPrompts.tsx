const prompts = [
  '帮我梳理今天最需要关注的健康问题',
  '根据我的情况给出一份健康管理建议',
  '帮我检查当前用药需要注意什么',
] as const

function fillComposer(value: string): void {
  const input = document.querySelector<HTMLTextAreaElement>('textarea')
  if (!input) return
  const setter = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype,
    'value',
  )?.set?.bind(input)
  if (setter !== undefined) setter(value)
  input.dispatchEvent(new InputEvent('input', {
    bubbles: true,
    data: value,
    inputType: 'insertText',
  }))
  input.focus()
}

export function QuickPrompts() {
  return (
    <div data-gerclaw-quick-prompts aria-label="快捷提问">
      {prompts.map(prompt => (
        <button
          key={prompt}
          type="button"
          title={prompt}
          onClick={() => { fillComposer(prompt) }}
        >
          {prompt}
        </button>
      ))}
    </div>
  )
}
