import { z } from "zod";

export const storedCitationSchema = z
  .object({
    source_id: z.string().min(1).max(256),
    title: z.string().min(1).max(512),
    locator: z.string().min(1).max(1_024),
    excerpt: z.string().min(1).max(2_000),
    score: z.number().min(0).nullable(),
    corpus: z.enum(["local_knowledge_base", "web", "uploaded_document", "uploaded_image"]),
  })
  .strict();
