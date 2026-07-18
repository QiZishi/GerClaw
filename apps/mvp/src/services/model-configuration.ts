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

const modelConfigurationSchema = z.object({
  revision: z.number().int().min(0),
  slots: z.array(z.object({
    preference,
    url: z.string().url(),
    model_name: z.string(),
    protocol,
    api_key_configured: z.literal(true),
    supports_image_input: z.boolean(),
    supports_tool_calling: z.boolean(),
    supports_structured_output: z.boolean(),
  }).strict()).max(3),
}).strict();

export type ModelSlot = z.infer<typeof modelSlotSchema>;
export type ModelConfiguration = z.infer<typeof modelConfigurationSchema>;

async function parse(response: Response): Promise<ModelConfiguration> {
  const data = modelConfigurationSchema.safeParse(await response.json().catch(() => null));
  if (!response.ok || !data.success) throw new Error("MODEL_CONFIGURATION_REQUEST_FAILED");
  return data.data;
}

export async function getModelConfiguration(): Promise<ModelConfiguration> {
  return parse(await fetch("/api/account/model-configuration", { cache: "no-store" }));
}

export async function saveModelConfiguration(revision: number, slots: ModelSlot[]): Promise<ModelConfiguration> {
  return parse(await fetch("/api/account/model-configuration", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_revision: revision, slots }),
  }));
}
