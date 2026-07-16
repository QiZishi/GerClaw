import "server-only";

type VoiceService = "asr" | "tts";

function readVoiceSetting(service: VoiceService, setting: "URL" | "MODEL"): string {
  const prefix = service === "asr" ? "ASR" : "TTS";
  return (
    process.env[`MIMO_${prefix}_${setting}`] ||
    process.env[`${prefix}_${setting}`] ||
    ""
  );
}

function readVoiceApiKey(service: VoiceService): string {
  const prefix = service === "asr" ? "ASR" : "TTS";
  return (
    process.env.MIMO_API_KEY ||
    process.env[`${prefix}_API_KEY`] ||
    ""
  );
}

export function getVoiceProvider(service: VoiceService) {
  return {
    url: readVoiceSetting(service, "URL"),
    apiKey: readVoiceApiKey(service),
    model: readVoiceSetting(service, "MODEL") || `mimo-v2.5-${service}`,
    voice:
      service === "tts"
        ? process.env.TTS_VOICE || "冰糖"
        : undefined,
  };
}

/** MiMo supports both the public api-key header and token-plan Bearer header. */
export function mimoAuthorizationHeaders(apiKey: string): Record<string, string> {
  const configuredHeader = (process.env.GERCLAW_MIMO_AUTH_HEADER || "authorization").toLowerCase();
  return configuredHeader === "api-key"
    ? { "api-key": apiKey }
    : { Authorization: `Bearer ${apiKey}` };
}
