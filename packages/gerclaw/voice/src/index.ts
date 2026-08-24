/** GerClaw voice interaction consumer, derived from dsh-talk 0.1.3. */
import { TalkService } from './service.ts'

export { Config, resolveConfig, type Config as TalkConfig, type ResolvedConfig } from './config.ts'
export { TalkService, resolveSttEngine, resolveTtsEngine, type StreamSpeakOptions } from './service.ts'
export { sanitizeText, redactSecrets, displayPath } from './sanitize.ts'
export type { TalkAudio, TalkInterruptResult, TalkStatus } from './wire.ts'
export type { DshTalkSpeechEvent, GerclawVoiceEvent, SpeechReason, SpeechTtsEngine } from './speech.ts'
export type { TalkSpeechProjection, TalkSpeechProjectionState } from './projection.ts'

export default TalkService
