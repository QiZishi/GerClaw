import type { Context } from '@deepseek-ai/cordis'
import productCss from './product.css?inline'

const PLUGIN_ID = '@gerclaw/client-ui'

export function installProductStyles(ctx: Context): void {
  if (typeof document === 'undefined') return
  ctx.effect(() => {
    const tag = document.createElement('style')
    tag.dataset.plugin = PLUGIN_ID
    tag.dataset.pluginCss = `${PLUGIN_ID}/product.css`
    tag.textContent = productCss
    document.head.appendChild(tag)
    return () => { tag.remove() }
  }, 'gerclaw client: product stylesheet')
}
