/**
 * `dsh-talk`, browser half: mounts the `talk` Remote contribution, registers
 * the composer microphone button into `conversation.input.left`, and the
 * settings tab (`settings.plugins.tab`, id `talk`). All data arrives through
 * the `remote.talk` namespace; the draft/send bindings come from the
 * conversation input face resolved for the session scope.
 *
 * @module dsh-talk/client
 */

import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
// Type-only: pulls the 'settings.plugins.tab' SlotMap declaration into this
// program so the tab registration typechecks against the real declaration.
// Type-only: pulls the 'conversation.input.left' SlotMap declaration in.
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { TalkMicInjected } from './TalkMicButton.tsx'
import { TalkMicButton } from './TalkMicButton.tsx'
import { installPlaybackInterruption, TalkMessageButton } from './TalkMessageButton.tsx'
import { en, zh, type TalkLocaleKey } from './locales.ts'
import { TALK_REMOTE } from './remote.ts'
import { installTalkStyles } from './styles.ts'
import { VoiceFileTranscriber } from './VoiceFileTranscriber.ts'

export type { TalkMicInjected, TalkMicProps } from './TalkMicButton.tsx'
export type { GerclawVoiceFiles, VoiceFileTranscriptionResult } from './VoiceFileTranscriber.ts'
export type { TalkLocaleKey } from './locales.ts'
export { foldMic, initMic, clampRecordSeconds, type MicEvent, type MicPhase, type MicViewModel } from './present.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Voice-loop settings copy. */
    'settings.talk': TalkLocaleKey
  }
}

/** Dictionary namespace owned by this plugin. */
export const NS = 'settings.talk'

/** Plugin name: matches the package name, the graph row id, and the bundle id. */
export const name = '@gerclaw/voice'

/** Services the browser half reads; `remote.talk` appears once the contribution mounts. */
export const inject = ['slots', 'locale', 'remote']

/**
 * Browser plugin body: dictionaries, the scoped stylesheet, the Remote
 * contribution mount, the mic-button slot, and the settings tab.
 *
 * @param ctx - client root context.
 */
export async function apply(ctx: ClientContext): Promise<void> {
  ctx.plugin(VoiceFileTranscriber)
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'dsh-talk: dictionaries')
  ctx.effect(() => installTalkStyles(), 'dsh-talk: stylesheet')
  ctx.effect(() => installPlaybackInterruption(), 'gerclaw voice: playback interruption')

  // $mount registers the 'remote.talk' namespace service and owns its removal.
  const disposeTalkRemote = await ctx.remote.$mount(TALK_REMOTE)
  ctx.effect(() => async () => { await disposeTalkRemote() }, 'gerclaw voice: talk remote')

  ctx.inject(['remote.talk'], (scope) => {
    const talk = scope.remote.talk
    const unwrap = <T>(result: { ok: boolean; value?: T; error?: { code?: string; message?: string } }, method: string): T => {
      if (!result.ok) {
        throw new Error(`talk.${method} failed: ${result.error?.code ?? 'unknown'}: ${result.error?.message ?? 'unknown'}`)
      }
      return result.value as T
    }
    const interrupt: TalkMicInjected['interrupt'] = async () =>
      unwrap(await talk.interrupt(), 'interrupt')
    scope.slots.inject('conversation.input.left', () => scope.slots.register({
      name: 'conversation.input.left',
      id: 'talk-mic',
      order: 20,
      inject: (): TalkMicInjected => ({ interrupt }),
    }, TalkMicButton))

    scope.slots.inject('conversation.chat.assistant-actions', () => scope.slots.register({
      name: 'conversation.chat.assistant-actions',
      id: 'gerclaw-read-aloud',
      order: 20,
    }, TalkMessageButton))
  })
}
