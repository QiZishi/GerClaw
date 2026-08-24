/**
 * `dsh-talk` — the voice-first session loop for DeepSeek Harness.
 *
 * Host half: mounts the `talk` Remote service (speak pipeline + audio cache
 * + settings write-back), registers the `speak` tool, registers the
 * `talk:speech` session-projection unit the web client plays utterances
 * from, and speaks event announcements:
 * - `agent/status` → `idle` after a `running` observation: turn complete.
 * - `agent/error`: a turn errored.
 * - `approval/request` (waterfall): an approval is pending — the listener
 *   announces without blocking and always calls `next()`.
 *
 * Function plugin — no default export (the Loader unwraps
 * `exports.default ?? exports`).
 *
 * @module dsh-talk
 */

import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-projection'
import { Config, resolveConfig } from './config.ts'
import {
  applyTalkSpeechProjection,
  initTalkSpeechProjection,
  TALK_SPEECH_PROJECTION_STATE_VERSION,
  talkSpeechProjectionSchema,
  viewTalkSpeechProjection,
} from './projection.ts'
import { TalkService } from './service.ts'
import { VoiceService as QianwenVoiceService } from './qianwen.ts'

export const name = 'talk'

export const inject = []

export { Config, resolveConfig, type Config as TalkConfig, type ResolvedConfig } from './config.ts'
export { TalkService, resolveSttEngine, resolveTtsEngine, type StreamSpeakOptions } from './service.ts'
export { VoiceService, type VoiceAudioChunk, type VoiceConfig } from './qianwen.ts'
export { sanitizeText, redactSecrets, displayPath } from './sanitize.ts'
export type { TalkAudio, TalkInterruptResult, TalkStatus } from './wire.ts'
export type { DshTalkSpeechEvent, GerclawVoiceEvent, SpeechReason, SpeechTtsEngine } from './speech.ts'
export type { TalkSpeechProjection, TalkSpeechProjectionState } from './projection.ts'

/**
 * Mount the plugin: the talk service, the speak tool, the projection unit,
 * and the three announcement listeners. Every registration is an effect on
 * this fiber, so unload/hot-reload removes the tool, the projection, and all
 * listeners together.
 *
 * @param ctx - context carrying tools + subprocess.
 * @param config - raw loader config; defaults applied through {@link resolveConfig}.
 */
export async function apply(ctx: Context, config: Config): Promise<void> {
  const resolved = resolveConfig(config)

  // GerClaw retains dsh-talk's complete session/projection/interrupt lifecycle,
  // while the account-local Qianwen provider owns all actual ASR/TTS traffic.
  // No browser speech or SiliconFlow path is registered here.
  // Mount the provider as a Cordis class plugin. Constructing a Service from a
  // function plugin only publishes the service field; class-plugin mounting is
  // what runs Service.init, where the account-local ASR upgrade route and its
  // unload disposer are installed.
  await ctx.plugin(QianwenVoiceService, config)

  // Mount as a class plugin so Cordis applies TalkService.static.inject before
  // constructing the Remote service. Direct construction from this parent
  // function fiber publishes `talk`, but does not grant the child context
  // access to the already mounted Qianwen provider.
  await ctx.plugin(TalkService, resolved)

  // The `talk:speech` projection unit: last-wins fold of spoken utterances,
  // read by the web client's record button through useProjection.
  ctx.inject(['sessionProjections'], (projectionCtx) => {
    projectionCtx.effect(() => projectionCtx.sessionProjections.register<'talk:speech', ReturnType<typeof initTalkSpeechProjection>>({
      key: 'talk:speech',
      stateSchema: talkSpeechProjectionSchema,
      init: initTalkSpeechProjection,
      apply: applyTalkSpeechProjection,
      wire: {
        viewSchema: talkSpeechProjectionSchema,
        view: viewTalkSpeechProjection,
      },
      stateVersion: TALK_SPEECH_PROJECTION_STATE_VERSION,
    }), 'dsh-talk: talk:speech projection')
  })

}
