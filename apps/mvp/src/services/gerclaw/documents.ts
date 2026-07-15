import { z } from "zod";
import { gerclawRequest } from "./client";
import {
  uploadedDocumentDeletedSchema,
  uploadedDocumentSchema,
  type UploadedDocument,
} from "./schemas";
import { ensureBackendSession } from "./skills";

const sourceSchema = z.enum(["mineru", "local_text"]);
const mediaTypeSchema = z.enum([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/markdown",
  "text/plain",
]);

export interface ParsedDocumentRegistration {
  localSessionId: string;
  filename: string;
  mediaType: string;
  source: "mineru" | "local-text";
  markdown: string;
}

export async function registerParsedDocument(
  input: ParsedDocumentRegistration
): Promise<UploadedDocument> {
  const sessionId = await ensureBackendSession(input.localSessionId);
  const mediaType = mediaTypeSchema.safeParse(input.mediaType);
  const source = sourceSchema.safeParse(input.source.replace("-", "_"));
  const filename = input.filename.trim();
  const markdown = input.markdown.trim();
  if (!mediaType.success || !source.success || !filename || !markdown) {
    throw new Error("文档信息不完整，无法安全加入本次对话");
  }
  return gerclawRequest("documents", uploadedDocumentSchema, {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      filename,
      media_type: mediaType.data,
      parse_source: source.data,
      markdown,
    }),
  });
}

export async function revokeParsedDocument(
  localSessionId: string,
  documentId: string
): Promise<void> {
  const sessionId = await ensureBackendSession(localSessionId);
  const parsedId = z.string().uuid().parse(documentId);
  await gerclawRequest(
    `documents/sessions/${encodeURIComponent(sessionId)}/${encodeURIComponent(parsedId)}`,
    uploadedDocumentDeletedSchema,
    { method: "DELETE" }
  );
}
