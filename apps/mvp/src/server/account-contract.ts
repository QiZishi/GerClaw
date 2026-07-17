import { z } from "zod";

/** The only session payload shape that the account BFF may turn into cookies. */
export const accountSessionSchema = z.object({
  access_token: z.string().min(32),
  refresh_token: z.string().min(32),
  token_type: z.literal("bearer"),
  expires_in: z.number().int().min(300).max(86_400),
  actor_id: z.string().regex(/^usr_account_[a-f0-9]{32}$/),
  role: z.enum(["patient", "doctor"]),
}).strict();
