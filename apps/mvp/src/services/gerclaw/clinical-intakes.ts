"use client";

import { z } from "zod";
import { GerclawApiError, gerclawRequest } from "./client";
import { ensureBackendSession } from "./skills";
import {
  clinicalIntakeSchema,
  fivePrescriptionDraftSchema,
  prescriptionDraftHistorySchema,
  medicationReconciliationSchema,
  medicationReviewDraftSchema,
  medicationReviewDraftHistorySchema,
  type ClinicalIntake,
  type FivePrescriptionDraft,
  type MedicationReconciliation,
  type MedicationReviewDraft,
  type MedicationReviewDraftHistory,
  type PrescriptionConversationTurn,
  type PrescriptionDraftHistory,
  prescriptionConversationTurnSchema,
} from "./schemas";
import type { ImageAttachment } from "@/types";
import { getGerclawVisitorId } from "./visitor";

const prescriptionCancellationSchema = z.object({
  trace_id: z.string().regex(/^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$/),
  status: z.literal("cancellation_requested"),
});

function toGerclawError(response: Response, traceId: string, payload: unknown): GerclawApiError {
  const detail = typeof payload === "object" && payload !== null
    ? ("error" in payload ? payload.error : "detail" in payload ? payload.detail : undefined)
    : undefined;
  const value = typeof detail === "object" && detail !== null ? detail : undefined;
  const message = value && "message" in value && typeof value.message === "string"
    ? value.message
    : "请求未完成，请稍后重试";
  const code = value && "code" in value && typeof value.code === "string"
    ? value.code
    : "GERCLAW_REQUEST_FAILED";
  return new GerclawApiError(message, code, response.status, traceId);
}

export type ClinicalIntakeKind = "prescription" | "medication_review";

export async function startClinicalIntake(input: {
  localSessionId: string;
  kind: ClinicalIntakeKind;
}): Promise<ClinicalIntake> {
  const sessionId = await ensureBackendSession(input.localSessionId);
  return gerclawRequest("clinical-intakes", clinicalIntakeSchema, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, kind: input.kind }),
  });
}

export async function getClinicalIntake(intakeId: string): Promise<ClinicalIntake> {
  return gerclawRequest(`clinical-intakes/${encodeURIComponent(intakeId)}`, clinicalIntakeSchema);
}

export async function getMedicationReconciliation(
  intakeId: string
): Promise<MedicationReconciliation> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(intakeId)}/medication-reconciliation`,
    medicationReconciliationSchema
  );
}

/** Generate a deterministic, source-traceable review; it is never a prescription. */
export async function generateMedicationReviewDraft(input: {
  intakeId: string;
  patientAge?: number;
}): Promise<MedicationReviewDraft> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(input.intakeId)}/medication-review-draft`,
    medicationReviewDraftSchema,
    {
      method: "POST",
      body: JSON.stringify(
        input.patientAge === undefined ? {} : { patient_age: input.patientAge }
      ),
    }
  );
}

/** Reopen encrypted source-bound review revisions for the current intake owner. */
export async function listMedicationReviewDrafts(
  intakeId: string
): Promise<MedicationReviewDraftHistory> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(intakeId)}/medication-review-drafts`,
    medicationReviewDraftHistorySchema
  );
}

/** Generate a source-bound draft; cancellation is only acknowledged by the governed API. */
export async function generatePrescriptionDraft(
  intakeId: string,
  options: { signal?: AbortSignal } = {}
): Promise<FivePrescriptionDraft> {
  const traceId = `trace_${crypto.randomUUID().replaceAll("-", "")}`;
  const transportController = new AbortController();
  let requestStarted = false;
  let cancellationConfirmed = false;
  let cancellationFailure: GerclawApiError | null = null;
  const requestCancellation = () => {
    if (!requestStarted || cancellationConfirmed || cancellationFailure) return;
    void (async () => {
      try {
        const response = await fetch(
          `/api/gerclaw/clinical-intakes/${encodeURIComponent(intakeId)}/prescription-draft/${encodeURIComponent(traceId)}/cancel`,
          {
            method: "POST",
            headers: {
              Accept: "application/json",
              "X-GerClaw-Visitor-ID": getGerclawVisitorId(),
            },
            credentials: "same-origin",
            cache: "no-store",
          }
        );
        const payload = await response.json().catch(() => null);
        if (!response.ok) throw toGerclawError(response, traceId, payload);
        const parsed = prescriptionCancellationSchema.safeParse(payload);
        if (!parsed.success || parsed.data.trace_id !== traceId) {
          throw new GerclawApiError("停止确认格式不正确", "PRESCRIPTION_CANCELLATION_INVALID", 502, traceId);
        }
        cancellationConfirmed = true;
        transportController.abort();
      } catch (error) {
        cancellationFailure = error instanceof GerclawApiError
          ? error
          : new GerclawApiError("暂时无法安全停止，请稍后重试", "PRESCRIPTION_CANCELLATION_UNAVAILABLE", 503, traceId);
        transportController.abort();
      }
    })();
  };
  options.signal?.addEventListener("abort", requestCancellation, { once: true });
  try {
    if (options.signal?.aborted) {
      throw new GerclawApiError("生成已在发送前停止。", "PRESCRIPTION_GENERATION_CANCELLED", 499, traceId);
    }
    requestStarted = true;
    const response = await fetch(`/api/gerclaw/clinical-intakes/${encodeURIComponent(intakeId)}/prescription-draft`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-GerClaw-Visitor-ID": getGerclawVisitorId(),
        "X-Trace-ID": traceId,
      },
      credentials: "same-origin",
      cache: "no-store",
      signal: transportController.signal,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw toGerclawError(response, traceId, payload);
    const parsed = fivePrescriptionDraftSchema.safeParse(payload);
    if (!parsed.success) {
      throw new GerclawApiError("后端响应格式不正确", "GERCLAW_RESPONSE_INVALID", 502, traceId);
    }
    return parsed.data;
  } catch (error) {
    if (cancellationConfirmed) {
      throw new GerclawApiError("已停止生成，未完成内容不会保存为草案。", "PRESCRIPTION_GENERATION_CANCELLED", 499, traceId);
    }
    if (cancellationFailure) throw cancellationFailure;
    throw error;
  } finally {
    options.signal?.removeEventListener("abort", requestCancellation);
  }
}

/** Read the newest persisted drafts belonging to this intake's current owner. */
export async function listPrescriptionDrafts(intakeId: string): Promise<PrescriptionDraftHistory> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(intakeId)}/prescription-drafts`,
    prescriptionDraftHistorySchema
  );
}

export async function processPrescriptionConversationTurn(input: {
  intakeId: string;
  expectedRevision: number;
  message: string;
  documentIds?: string[];
  images?: ImageAttachment[];
}): Promise<PrescriptionConversationTurn> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(input.intakeId)}/conversation-turn`,
    prescriptionConversationTurnSchema,
    {
      method: "POST",
      body: JSON.stringify({
        expected_revision: input.expectedRevision,
        message: input.message,
        ...(input.documentIds === undefined ? {} : { document_ids: input.documentIds }),
        images: (input.images ?? []).map((image) => ({
          media_type: image.mimeType,
          base64: image.base64,
        })),
      }),
    }
  );
}

export async function updateClinicalIntake(input: {
  intakeId: string;
  expectedRevision: number;
  answers: Record<string, string>;
  documentIds?: string[];
  conversationTurnIncrement?: 1;
}): Promise<ClinicalIntake> {
  return gerclawRequest(`clinical-intakes/${encodeURIComponent(input.intakeId)}`, clinicalIntakeSchema, {
    method: "PATCH",
    body: JSON.stringify({
      expected_revision: input.expectedRevision,
      answers: input.answers,
      ...(input.documentIds === undefined ? {} : { document_ids: input.documentIds }),
      ...(input.conversationTurnIncrement === undefined
        ? {}
        : { conversation_turn_increment: input.conversationTurnIncrement }),
    }),
  });
}
