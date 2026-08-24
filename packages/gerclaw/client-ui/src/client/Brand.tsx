import type { HeroBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { SidebarBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-sidebar/client'

type BrandMarkProps = HeroBrandMarkOwnerProps & SidebarBrandMarkOwnerProps

export function GerclawBrandMark({ size, className }: BrandMarkProps) {
  return (
    <img
      data-gerclaw-logo
      className={className}
      src="/brand-icon.png"
      width={size}
      height={size}
      alt=""
      aria-hidden="true"
    />
  )
}

export function GerclawBrandName() {
  return (
    <span data-gerclaw-brand-name>
      <strong>GerClaw</strong>
      <span>老年慢病智慧诊疗助手</span>
    </span>
  )
}
