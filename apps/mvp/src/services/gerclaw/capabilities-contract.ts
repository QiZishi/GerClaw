import { z } from "zod";

const jsonValueSchema: z.ZodType<unknown> = z.lazy(() =>
  z.union([
    z.string(),
    z.number().finite(),
    z.boolean(),
    z.null(),
    z.array(jsonValueSchema),
    z.record(z.string(), jsonValueSchema),
  ])
);

export const capabilityManifestSchema = z
  .object({
    schema_version: z.literal("1.0"),
    capability_id: z.string().regex(/^[a-z][a-z0-9_.-]{1,127}$/),
    version: z.string().min(1).max(64),
    display_name: z.string().min(1).max(128),
    risk_level: z.enum(["low", "medium", "high"]),
    owner_module: z.string().regex(/^[a-z][a-z0-9_]{1,63}$/),
    entrypoint: z.enum([
      "cga_assessment",
      "medication_review_intake",
      "five_prescription_intake",
      "run_artifact",
    ]),
    automatic_selection: z.boolean(),
    manual_selection: z.boolean(),
    supported_workflows: z.array(z.string().min(1).max(32)).max(10),
    required_tools: z.array(z.string().min(1).max(128)).max(50),
    shared_result_kinds: z.array(z.string().min(1).max(64)).max(20),
    input_schema: z.record(z.string(), jsonValueSchema),
    output_schema: z.record(z.string(), jsonValueSchema),
  })
  .strict();

export const capabilityCatalogSchema = z
  .object({ capabilities: z.array(capabilityManifestSchema).max(50) })
  .strict();

export type CapabilityManifest = z.infer<typeof capabilityManifestSchema>;
