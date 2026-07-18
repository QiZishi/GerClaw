import { z } from "zod";

const preference = z.enum(["primary", "backup1", "backup2"]);
const protocol = z.enum(["openai", "dashscope", "anthropic"]);

export const modelSlotSchema = z.object({
  preference,
  url: z.string().url(),
  api_key: z.string().min(1).max(2048),
  model_name: z.string().min(1).max(128),
  protocol,
  supports_image_input: z.boolean(),
  supports_tool_calling: z.boolean(),
  supports_structured_output: z.boolean(),
}).strict();

const searchWrite = z.object({
  anysearch_url: z.string().url().optional(),
  anysearch_api_key: z.string().min(1).max(2048).optional(),
  tavily_url: z.string().url().optional(),
  tavily_api_key: z.string().min(1).max(2048).optional(),
}).strict();

const vectorWrite = z.object({
  url: z.string().url(), api_key: z.string().min(1).max(2048),
  embedding_model: z.string().min(1).max(128), rerank_model: z.string().min(1).max(128),
}).strict();

const voiceWrite = z.object({
  api_key: z.string().min(1).max(2048), asr_url: z.string().url(), asr_model: z.string().min(1).max(128),
  tts_url: z.string().url(), tts_model: z.string().min(1).max(128), tts_voice: z.string().min(1).max(64),
}).strict();

const mineruWrite = z.object({ url: z.string().url(), api_key: z.string().min(1).max(2048) }).strict();

export const serviceOverridesSchema = z.object({
  search: searchWrite.optional(), vector: vectorWrite.optional(), voice: voiceWrite.optional(), mineru: mineruWrite.optional(),
}).strict();

const searchRead = z.object({
  anysearch_url: z.string().url().nullable(), anysearch_api_key_configured: z.boolean(),
  tavily_url: z.string().url().nullable(), tavily_api_key_configured: z.boolean(),
}).strict();
const vectorRead = z.object({ url: z.string().url(), api_key_configured: z.literal(true), embedding_model: z.string(), rerank_model: z.string() }).strict();
const voiceRead = z.object({
  api_key_configured: z.literal(true), asr_url: z.string().url(), asr_model: z.string(),
  tts_url: z.string().url(), tts_model: z.string(), tts_voice: z.string(),
}).strict();
const mineruRead = z.object({ url: z.string().url(), api_key_configured: z.literal(true) }).strict();
const serviceOverridesRead = z.object({ search: searchRead.nullable(), vector: vectorRead.nullable(), voice: voiceRead.nullable(), mineru: mineruRead.nullable() }).strict();

const modelConfigurationSchema = z.object({
  revision: z.number().int().min(0),
  slots: z.array(z.object({
    preference, url: z.string().url(), model_name: z.string(), protocol,
    api_key_configured: z.literal(true), supports_image_input: z.boolean(), supports_tool_calling: z.boolean(), supports_structured_output: z.boolean(),
  }).strict()).max(3),
  services: serviceOverridesRead,
}).strict();

export type ModelSlot = z.infer<typeof modelSlotSchema>;
export type ServiceOverrides = z.infer<typeof serviceOverridesSchema>;
export type ModelConfiguration = z.infer<typeof modelConfigurationSchema>;

async function parse(response: Response): Promise<ModelConfiguration> {
  const data = modelConfigurationSchema.safeParse(await response.json().catch(() => null));
  if (!response.ok || !data.success) throw new Error("MODEL_CONFIGURATION_REQUEST_FAILED");
  return data.data;
}

export async function getModelConfiguration(): Promise<ModelConfiguration> {
  return parse(await fetch("/api/account/model-configuration", { cache: "no-store" }));
}

export async function saveModelConfiguration(revision: number, slots: ModelSlot[], services: ServiceOverrides): Promise<ModelConfiguration> {
  return parse(await fetch("/api/account/model-configuration", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_revision: revision, slots, services }),
  }));
}
