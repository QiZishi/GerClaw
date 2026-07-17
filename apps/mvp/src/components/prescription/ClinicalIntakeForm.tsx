"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Paperclip,
  Save,
  SearchCheck,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";
import { GerclawApiError } from "@/services/gerclaw/client";
import {
  getClinicalIntake,
  getMedicationReconciliation,
  generateMedicationReviewDraft,
  generatePrescriptionDraft,
  startClinicalIntake,
  updateClinicalIntake,
  type ClinicalIntakeKind,
} from "@/services/gerclaw/clinical-intakes";
import type {
  ClinicalIntake,
  FivePrescriptionDraft,
  MedicationReconciliation,
  MedicationReviewDraft,
} from "@/services/gerclaw/schemas";
import { parseFile } from "@/services/document/mineru";
import { registerParsedDocument, revokeParsedDocument } from "@/services/gerclaw/documents";

const DOCUMENT_ACCEPT = ".pdf,.docx,.md,.txt";

function documentMediaType(file: File): string | null {
  if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
    return "application/pdf";
  }
  if (
    file.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    file.name.toLowerCase().endsWith(".docx")
  ) {
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  }
  if (file.type === "text/markdown" || file.name.toLowerCase().endsWith(".md")) {
    return "text/markdown";
  }
  if (file.type === "text/plain" || file.name.toLowerCase().endsWith(".txt")) {
    return "text/plain";
  }
  return null;
}

const intakeStorageKey = (sessionId: string, kind: ClinicalIntakeKind) =>
  `gerclaw:clinical-intake:${sessionId}:${kind}`;

function formatElapsed(elapsedSeconds: number): string {
  const normalizedSeconds = Math.max(0, elapsedSeconds);
  const minutes = Math.floor(normalizedSeconds / 60);
  const seconds = normalizedSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function medicationSeverityLabel(severity: MedicationReviewDraft["findings"][number]["severity"]): string {
  return {
    contraindicated: "禁忌",
    major: "严重",
    moderate: "中等",
    minor: "轻微",
  }[severity];
}

function medicationSeverityClass(severity: MedicationReviewDraft["findings"][number]["severity"]): string {
  return {
    contraindicated: "border-red-600/50 bg-red-50 text-red-950 dark:bg-red-950/25 dark:text-red-100",
    major: "border-orange-600/50 bg-orange-50 text-orange-950 dark:bg-orange-950/25 dark:text-orange-100",
    moderate: "border-amber-500/50 bg-amber-50 text-amber-950 dark:bg-amber-950/25 dark:text-amber-100",
    minor: "border-blue-600/40 bg-blue-50 text-blue-950 dark:bg-blue-950/25 dark:text-blue-100",
  }[severity];
}

function readStoredIntakeId(sessionId: string, kind: ClinicalIntakeKind): string | null {
  try {
    const value = window.localStorage.getItem(intakeStorageKey(sessionId, kind));
    return value && /^[0-9a-f-]{36}$/i.test(value) ? value : null;
  } catch {
    return null;
  }
}

function storeIntakeId(sessionId: string, kind: ClinicalIntakeKind, intakeId: string): void {
  try {
    window.localStorage.setItem(intakeStorageKey(sessionId, kind), intakeId);
  } catch {
    // The durable server record remains usable; this UUID is only a resume optimization.
  }
}

function clearStoredIntakeId(sessionId: string, kind: ClinicalIntakeKind): void {
  try {
    window.localStorage.removeItem(intakeStorageKey(sessionId, kind));
  } catch {
    // Ignore storage limitations; never treat browser storage as workflow truth.
  }
}

interface ClinicalIntakeFormProps {
  localSessionId: string;
  kind: ClinicalIntakeKind;
  seniorMode: boolean;
  onExit: () => void;
  onPrescriptionDraftGenerated?: (draft: FivePrescriptionDraft) => void;
}

export function ClinicalIntakeForm({
  localSessionId,
  kind,
  seniorMode,
  onExit,
  onPrescriptionDraftGenerated,
}: ClinicalIntakeFormProps) {
  const [intake, setIntake] = useState<ClinicalIntake | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [saving, setSaving] = useState(false);
  const [documentState, setDocumentState] = useState<"idle" | "parsing" | "saving">("idle");
  const [documentElapsedSeconds, setDocumentElapsedSeconds] = useState(0);
  const [draft, setDraft] = useState<FivePrescriptionDraft | null>(null);
  const [draftState, setDraftState] = useState<"idle" | "generating">("idle");
  const [draftElapsedSeconds, setDraftElapsedSeconds] = useState(0);
  const [documentNames, setDocumentNames] = useState<Record<string, string>>({});
  const [reloadNonce, setReloadNonce] = useState(0);
  const [showValidation, setShowValidation] = useState(false);
  const [medicationReconciliation, setMedicationReconciliation] =
    useState<MedicationReconciliation | null>(null);
  const [medicationReviewDraft, setMedicationReviewDraft] =
    useState<MedicationReviewDraft | null>(null);
  const [medicationReviewState, setMedicationReviewState] = useState<"idle" | "generating">("idle");
  const [medicationReviewElapsedSeconds, setMedicationReviewElapsedSeconds] = useState(0);
  const [patientAge, setPatientAge] = useState("");
  const fieldRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});
  const documentInputRef = useRef<HTMLInputElement>(null);
  const pendingStartRef = useRef<{
    key: string;
    promise: Promise<ClinicalIntake>;
  } | null>(null);

  useEffect(() => {
    if (documentState === "idle") return;
    const timer = window.setInterval(
      () => setDocumentElapsedSeconds((elapsed) => elapsed + 1),
      1_000
    );
    return () => window.clearInterval(timer);
  }, [documentState]);

  useEffect(() => {
    if (draftState !== "generating") return;
    const timer = window.setInterval(
      () => setDraftElapsedSeconds((elapsed) => elapsed + 1),
      1_000
    );
    return () => window.clearInterval(timer);
  }, [draftState]);

  useEffect(() => {
    if (medicationReviewState !== "generating") return;
    const timer = window.setInterval(
      () => setMedicationReviewElapsedSeconds((elapsed) => elapsed + 1),
      1_000
    );
    return () => window.clearInterval(timer);
  }, [medicationReviewState]);

  useEffect(() => {
    let live = true;
    const load = async () => {
      setLoadState("loading");
      const savedId = readStoredIntakeId(localSessionId, kind);
      const startOrJoin = (): Promise<ClinicalIntake> => {
        const key = `${localSessionId}:${kind}`;
        const pending = pendingStartRef.current;
        if (pending?.key === key) return pending.promise;

        const promise = startClinicalIntake({ localSessionId, kind });
        pendingStartRef.current = { key, promise };
        void promise.then(
          () => {
            if (pendingStartRef.current?.promise === promise) {
              pendingStartRef.current = null;
            }
          },
          () => {
            if (pendingStartRef.current?.promise === promise) {
              pendingStartRef.current = null;
            }
          }
        );
        return promise;
      };
      try {
        let next: ClinicalIntake;
        if (savedId) {
          try {
            next = await getClinicalIntake(savedId);
          } catch (error) {
            // A browser can retain an intake id after an account/session reset.
            // Only a confirmed missing record may start a new intake: never turn a
            // transient authorization or network failure into a duplicate record.
            if (!(error instanceof GerclawApiError) || error.code !== "CLINICAL_INTAKE_NOT_FOUND") {
              throw error;
            }
            clearStoredIntakeId(localSessionId, kind);
            next = await startOrJoin();
          }
        } else {
          next = await startOrJoin();
        }
        if (!live) return;
        storeIntakeId(localSessionId, kind, next.intake_id);
        setMedicationReconciliation(null);
        setMedicationReviewDraft(null);
        setDraft(null);
        setIntake(next);
        setAnswers(next.answers);
        setDocumentNames((previous) => {
          const retained = Object.fromEntries(
            Object.entries(previous).filter(([documentId]) => next.document_ids.includes(documentId))
          );
          return retained;
        });
        setLoadState("ready");
      } catch (error) {
        if (!live) return;
        if (savedId) {
          clearStoredIntakeId(localSessionId, kind);
        }
        setLoadState("error");
        toast.show(error instanceof Error ? error.message : "信息收集暂时不可用，请稍后重试");
      }
    };
    void load();
    return () => {
      live = false;
    };
  }, [kind, localSessionId, reloadNonce]);

  useEffect(() => {
    if (kind !== "medication_review" || !intake) return;
    let live = true;
    void getMedicationReconciliation(intake.intake_id).then(
      (result) => {
        if (live) setMedicationReconciliation(result);
      },
      () => {
        // The collection form remains usable if this optional read view is unavailable.
        if (live) setMedicationReconciliation(null);
      }
    );
    return () => {
      live = false;
    };
  }, [intake, kind]);

  const save = async () => {
    if (!intake || saving) return;
    const missingRequiredFields = intake.fields.filter(
      (field) => field.required && !(answers[field.id] ?? "").trim()
    );
    if (missingRequiredFields.length > 0) {
      setShowValidation(true);
      fieldRefs.current[missingRequiredFields[0].id]?.focus();
      return;
    }
    setSaving(true);
    try {
      const next = await updateClinicalIntake({
        intakeId: intake.intake_id,
        expectedRevision: intake.revision,
        answers,
      });
      setIntake(next);
      setAnswers(next.answers);
      setDraft(null);
      setMedicationReviewDraft(null);
      if (next.kind === "medication_review") {
        toast.show("信息已保存，可以开始规则审查。", 1_800);
      } else {
        toast.show(
          next.status === "information_complete_pending_governance"
            ? "信息已保存；现在可以生成待临床复核的五大处方草案"
            : "信息已保存，您可以继续补充"
        );
      }
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "信息暂未保存，请检查网络后重试");
    } finally {
      setSaving(false);
    }
  };

  const updateDocumentReferences = async (documentIds: string[]) => {
    if (!intake || saving || documentState !== "idle") return;
    setDocumentElapsedSeconds(0);
    setDocumentState("saving");
    try {
      const next = await updateClinicalIntake({
        intakeId: intake.intake_id,
        expectedRevision: intake.revision,
        answers: {},
        documentIds,
      });
      setIntake(next);
      setDraft(null);
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "资料关联暂未保存，请重试");
    } finally {
      setDocumentState("idle");
      setDocumentElapsedSeconds(0);
    }
  };

  const attachDocument = async (file: File | undefined) => {
    if (!file || !intake || saving || documentState !== "idle") return;
    const mediaType = documentMediaType(file);
    if (!mediaType) {
      toast.show("仅支持 PDF、Word、Markdown 或文本资料");
      return;
    }
    setDocumentElapsedSeconds(0);
    setDocumentState("parsing");
    let registeredDocumentId: string | null = null;
    try {
      const parsed = await parseFile(file);
      // MinerU extraction is already complete. Keep the next write visibly
      // distinct so a long registration does not look like a stalled parser.
      setDocumentState("saving");
      const registered = await registerParsedDocument({
        localSessionId,
        filename: file.name,
        mediaType,
        source: parsed.source,
        markdown: parsed.markdown,
      });
      registeredDocumentId = registered.document_id;
      const documentIds = [...intake.document_ids, registered.document_id];
      const next = await updateClinicalIntake({
        intakeId: intake.intake_id,
        expectedRevision: intake.revision,
        answers: {},
        documentIds,
      });
      setIntake(next);
      setDraft(null);
      setDocumentNames((previous) => ({ ...previous, [registered.document_id]: file.name }));
      toast.show("资料已通过 MinerU 提取文本，并作为本次信息收集的输入保存");
    } catch (error) {
      if (registeredDocumentId) {
        try {
          await revokeParsedDocument(localSessionId, registeredDocumentId);
        } catch {
          // Do not mask the original association failure; server-side ownership
          // checks still prevent this document from reaching another session.
        }
      }
      toast.show(error instanceof Error ? error.message : "资料解析或保存失败，请重试");
    } finally {
      setDocumentState("idle");
      setDocumentElapsedSeconds(0);
    }
  };

  const generateDraft = async () => {
    if (!intake || intake.kind !== "prescription" || draftState === "generating") return;
    setDraftElapsedSeconds(0);
    setDraftState("generating");
    try {
      const next = await generatePrescriptionDraft(intake.intake_id);
      setDraft(next);
      onPrescriptionDraftGenerated?.(next);
      toast.show("五大处方待临床复核草案已生成，请先查看证据和注意事项");
    } catch (error) {
      if (error instanceof GerclawApiError) {
        const messages: Record<string, string> = {
          PRESCRIPTION_EVIDENCE_UNAVAILABLE: "本地医学证据暂未就绪，系统不会在没有证据时生成草案。",
          PRESCRIPTION_DRAFT_UNAVAILABLE: "生成服务暂时不可用；您的信息已安全保存，可稍后重试。",
          PRESCRIPTION_EMERGENCY_BLOCKED: "检测到可能需要紧急就医的情况，已停止生成草案，请优先寻求线下医疗帮助。",
          PRESCRIPTION_INPUT_NOT_READY: "请确认必填信息和上传资料仍有效后，再生成草案。",
        };
        toast.show(messages[error.code] ?? "草案暂时无法生成；您的信息已安全保存，可稍后重试。");
      } else {
        toast.show("草案暂时无法生成；您的信息已安全保存，可稍后重试。");
      }
    } finally {
      setDraftState("idle");
      setDraftElapsedSeconds(0);
    }
  };

  const generateMedicationReview = async () => {
    if (!intake || intake.kind !== "medication_review" || medicationReviewState === "generating") return;
    const normalizedAge = patientAge.trim();
    const age = normalizedAge === "" ? undefined : Number(normalizedAge);
    if (age !== undefined && (!Number.isInteger(age) || age < 0 || age > 130)) {
      toast.show("患者年龄请填写 0 到 130 之间的整数；不确定时可留空。 ");
      return;
    }
    setMedicationReviewElapsedSeconds(0);
    setMedicationReviewState("generating");
    try {
      const next = await generateMedicationReviewDraft({
        intakeId: intake.intake_id,
        patientAge: age,
      });
      setMedicationReviewDraft(next);
      toast.show("用药审查已完成，请查看禁忌、严重风险和规则覆盖范围。", 1_800);
    } catch (error) {
      if (error instanceof GerclawApiError && error.code === "MEDICATION_REVIEW_INPUT_INVALID") {
        toast.show("请先保存至少一条正在使用的药物，再进行用药审查。");
      } else {
        toast.show("用药审查暂时无法完成；您的信息没有被修改，请稍后重试。");
      }
    } finally {
      setMedicationReviewState("idle");
      setMedicationReviewElapsedSeconds(0);
    }
  };

  const actionClass = seniorMode ? "min-h-12 px-5 text-lg" : "min-h-10 px-4";

  if (loadState === "loading") {
    return (
      <section className="flex flex-1 items-center justify-center p-6" aria-live="polite">
        <p className={cn("text-muted-foreground", seniorMode && "text-lg")}>
          正在安全读取信息收集表…
        </p>
      </section>
    );
  }

  if (loadState === "error" || !intake) {
    return (
      <section className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
        <AlertTriangle className="size-8 text-amber-600" />
        <p className={cn("max-w-md text-muted-foreground", seniorMode && "text-lg")}>
          暂时无法开始信息收集。不会生成任何处方或用药结论。
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button variant="outline" className={actionClass} onClick={() => setReloadNonce((value) => value + 1)}>重新尝试</Button>
          <Button className={actionClass} onClick={onExit}>返回健康咨询</Button>
        </div>
      </section>
    );
  }

  const complete = intake.status === "information_complete_pending_governance";
  const hasUnsavedChanges = intake.fields.some(
    (field) => (answers[field.id] ?? "") !== (intake.answers[field.id] ?? "")
  );
  const missingRequiredFieldIds = new Set(
    intake.fields
      .filter((field) => field.required && !(answers[field.id] ?? "").trim())
      .map((field) => field.id)
  );
  const missingRequiredLabels = intake.fields
    .filter((field) => missingRequiredFieldIds.has(field.id))
    .map((field) => field.label);
  return (
    <section className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-5 overflow-y-auto p-4 md:p-6">
      <header className="space-y-2">
        <h1 className={cn("font-semibold text-foreground", seniorMode ? "text-2xl" : "text-xl")}>
          {intake.title}
        </h1>
        <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-base")}>
          {intake.description}
        </p>
      </header>

      <div className="rounded-xl border border-amber-500/40 bg-amber-50/70 p-4 text-amber-950 dark:bg-amber-950/20 dark:text-amber-100">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 size-5 shrink-0" />
          <p className={cn("leading-relaxed", seniorMode ? "text-lg" : "text-sm")}>
            {intake.governance_notice}
          </p>
        </div>
      </div>

      <div className="space-y-5">
        {showValidation && missingRequiredLabels.length > 0 && (
          <div
            className={cn("rounded-xl border border-destructive/50 bg-destructive/10 p-4 text-destructive", seniorMode ? "text-lg" : "text-sm")}
            role="alert"
          >
            请先填写必填内容：{missingRequiredLabels.join("、")}。
          </div>
        )}
        {intake.fields.map((field) => (
          <label key={field.id} className="block space-y-2">
            <span className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-base")}>
              {field.label}{field.required ? "（必填）" : "（可选）"}
            </span>
            <textarea
              ref={(node) => {
                fieldRefs.current[field.id] = node;
              }}
              value={answers[field.id] ?? ""}
              onChange={(event) => setAnswers((previous) => ({ ...previous, [field.id]: event.target.value.slice(0, field.max_length) }))}
              placeholder={field.placeholder}
              disabled={saving}
              rows={seniorMode ? 4 : 3}
              maxLength={field.max_length}
              aria-invalid={showValidation && missingRequiredFieldIds.has(field.id)}
              aria-describedby={showValidation && missingRequiredFieldIds.has(field.id) ? `clinical-intake-${field.id}-error` : undefined}
              className={cn(
                "w-full resize-y rounded-xl border border-input bg-background px-4 py-3 leading-relaxed outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60",
                showValidation && missingRequiredFieldIds.has(field.id) && "border-destructive focus:border-destructive focus:ring-destructive/20",
                seniorMode ? "min-h-28 text-lg" : "min-h-24 text-base"
              )}
            />
            {showValidation && missingRequiredFieldIds.has(field.id) && (
              <span id={`clinical-intake-${field.id}-error`} className={cn("block text-destructive", seniorMode ? "text-lg" : "text-sm")}>
                请填写“{field.label}”后再保存。
              </span>
            )}
          </label>
        ))}

        {kind === "prescription" && (
          <section className="space-y-3 rounded-xl border border-primary/25 bg-primary/5 p-4" aria-labelledby="prescription-documents-title">
            <div className="flex items-start gap-3">
              <FileText className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
              <div className="min-w-0 space-y-1">
                <h2 id="prescription-documents-title" className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-base")}>
                  补充资料（可选）
                </h2>
                <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                  PDF、Word、Markdown 或文本会先由 MinerU 提取文本，作为本次草案的患者输入与“上传资料依据”。它不会被当作本地医学知识库证据。
                </p>
              </div>
            </div>
            <input
              ref={documentInputRef}
              className="hidden"
              type="file"
              accept={DOCUMENT_ACCEPT}
              tabIndex={-1}
              aria-hidden="true"
              onChange={(event) => {
                void attachDocument(event.target.files?.[0]);
                event.target.value = "";
              }}
              disabled={saving || documentState !== "idle" || intake.document_ids.length >= 5}
            />
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="button"
                variant="outline"
                className={actionClass}
                onClick={() => documentInputRef.current?.click()}
                disabled={saving || documentState !== "idle" || intake.document_ids.length >= 5}
              >
                {documentState === "parsing" || documentState === "saving" ? (
                  <span className="codex-activity-dots text-primary" aria-hidden="true">
                    <span className="codex-activity-dot" />
                    <span className="codex-activity-dot" />
                    <span className="codex-activity-dot" />
                  </span>
                ) : (
                  <Paperclip className="size-4" aria-hidden="true" />
                )}
                {documentState === "parsing"
                  ? `正在用 MinerU 解析 · 已等待 ${formatElapsed(documentElapsedSeconds)}`
                  : documentState === "saving"
                    ? `正在保存资料 · 已等待 ${formatElapsed(documentElapsedSeconds)}`
                    : "上传补充资料"}
              </Button>
              <span className={cn("text-muted-foreground", seniorMode ? "text-lg" : "text-sm")} aria-live="polite">
                已附 {intake.document_ids.length} / 5 份资料
              </span>
            </div>
            {intake.document_ids.length > 0 && (
              <ul className="space-y-2" aria-label="本次信息收集使用的上传资料">
                {intake.document_ids.map((documentId, index) => (
                  <li key={documentId} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2">
                    <span className={cn("min-w-0 break-all text-foreground", seniorMode ? "text-lg" : "text-sm")}>
                      {documentNames[documentId] ?? `已关联的上传资料 ${index + 1}`}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size={seniorMode ? "default" : "sm"}
                      className={cn("shrink-0 text-muted-foreground", seniorMode && "min-h-12 px-3 text-base")}
                      onClick={() => void updateDocumentReferences(intake.document_ids.filter((item) => item !== documentId))}
                      disabled={saving || documentState !== "idle"}
                    >
                      不用于本次收集
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {kind === "medication_review" && (
          <section
            className="space-y-3 rounded-xl border border-primary/25 bg-primary/5 p-4"
            aria-labelledby="medication-reconciliation-title"
          >
            <div className="flex items-start gap-3">
              <SearchCheck className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
              <div className="space-y-1">
                <h2
                  id="medication-reconciliation-title"
                  className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-base")}
                >
                  用药规则审查
                </h2>
                <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                  先核对录入，再按已安装、可追溯的有限规则生成待复核结果。
                </p>
              </div>
            </div>
            {medicationReconciliation?.has_medication_list ? (
              <>
                {medicationReconciliation.exact_duplicate_candidates.length > 0 ? (
                  <div className="rounded-lg border border-amber-500/40 bg-amber-50/70 p-3 text-amber-950 dark:bg-amber-950/20 dark:text-amber-100">
                    <p className={cn("font-medium", seniorMode ? "text-lg" : "text-sm")}>
                      发现 {medicationReconciliation.exact_duplicate_candidates.length} 组完全相同的录入项
                    </p>
                    <ul className={cn("mt-2 space-y-1 leading-relaxed", seniorMode ? "text-lg" : "text-sm")}>
                      {medicationReconciliation.exact_duplicate_candidates.map((candidate) => (
                        <li key={`${candidate.text}-${candidate.positions.join("-")}`}>
                          第 {candidate.positions.join("、")} 项内容相同，请带药盒请医生或药师核对。
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className={cn("rounded-lg border border-border bg-background p-3 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                    暂未发现完全相同的录入项。不同名称、同类药或剂量问题仍需要医生或药师核对。
                  </p>
                )}
                <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                  {medicationReconciliation.notice}
                </p>
              </>
            ) : (
              <p className={cn("rounded-lg border border-border bg-background p-3 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                填写并保存“正在使用的药物”后，可在这里查看录入核对结果。
              </p>
            )}
            <div className="space-y-3 border-t border-primary/15 pt-4">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <label className="block min-w-40 space-y-1.5">
                  <span className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-sm")}>患者年龄（可选）</span>
                  <input
                    inputMode="numeric"
                    type="text"
                    value={patientAge}
                    onChange={(event) => setPatientAge(event.target.value.replace(/\D/g, "").slice(0, 3))}
                    disabled={saving || medicationReviewState === "generating"}
                    placeholder="不确定可留空"
                    className={cn(
                      "h-11 w-full rounded-lg border border-input bg-background px-3 text-foreground outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60",
                      seniorMode && "min-h-12 text-lg"
                    )}
                  />
                </label>
                <Button
                  type="button"
                  className={actionClass}
                  onClick={() => void generateMedicationReview()}
                  disabled={
                    saving ||
                    hasUnsavedChanges ||
                    !medicationReconciliation?.has_medication_list ||
                    medicationReviewState === "generating"
                  }
                >
                  {medicationReviewState === "generating" ? (
                    <span className="inline-flex items-center gap-2" aria-live="polite">
                      <span className="codex-activity-dots" aria-hidden="true">
                        <span className="codex-activity-dot" />
                        <span className="codex-activity-dot" />
                        <span className="codex-activity-dot" />
                      </span>
                      审查中 · {formatElapsed(medicationReviewElapsedSeconds)}
                    </span>
                  ) : (
                    "开始规则审查"
                  )}
                </Button>
              </div>
              {hasUnsavedChanges && (
                <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                  请先保存对药物列表的修改，再进行规则审查，避免审查到旧信息。
                </p>
              )}
              <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                审查只使用已安装、可追溯的本地规则；不会把药物列表发送给大模型。结果供医师或药师复核，不能自行改药。
              </p>
              {medicationReviewDraft && (
                <div className="space-y-3 rounded-lg border border-primary/30 bg-background p-3" aria-live="polite">
                  <div className="space-y-1">
                    <p className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-sm")}>
                      规则审查结果 · {medicationReviewDraft.ruleset_version}
                    </p>
                    <p className={cn("leading-relaxed text-foreground", seniorMode ? "text-lg" : "text-sm")}>
                      {medicationReviewDraft.conclusion}
                    </p>
                  </div>
                  <p className={cn("rounded-md border border-amber-500/40 bg-amber-50/70 p-3 text-amber-950 dark:bg-amber-950/20 dark:text-amber-100", seniorMode ? "text-lg" : "text-sm")}>
                    Beers 筛查：尚未安装可授权、可审计的规则来源，因此本次没有执行 Beers 判断；“未命中”不等于安全。
                  </p>
                  {medicationReviewDraft.unrecognized_entry_count > 0 && (
                    <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                      有 {medicationReviewDraft.unrecognized_entry_count} 条药物未被当前有限词表识别，不能完成其完整交互检查。
                    </p>
                  )}
                  {medicationReviewDraft.findings.length > 0 ? (
                    <ul className="space-y-2" aria-label="用药审查发现">
                      {medicationReviewDraft.findings.map((finding) => (
                        <li key={finding.finding_id} className={cn("space-y-2 rounded-lg border p-3", medicationSeverityClass(finding.severity))}>
                          <p className={cn("font-medium", seniorMode ? "text-lg" : "text-sm")}>
                            【{medicationSeverityLabel(finding.severity)}】{finding.title}
                            {finding.age_escalated ? "（因年龄≥75岁已升级）" : ""}
                          </p>
                          <p className={cn("leading-relaxed", seniorMode ? "text-lg" : "text-sm")}>{finding.conclusion}</p>
                          <p className={cn("leading-relaxed", seniorMode ? "text-lg" : "text-sm")}>复核建议：{finding.clinician_action}</p>
                          {finding.elderly_note && <p className={cn("leading-relaxed", seniorMode ? "text-lg" : "text-sm")}>老年提示：{finding.elderly_note}</p>}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className={cn("rounded-md border border-border p-3 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                      当前有限规则未命中风险；请仍由医师或药师完成完整核对。
                    </p>
                  )}
                  <details className={cn("rounded-md border border-border p-3 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                    <summary className="cursor-pointer font-medium text-foreground">查看规则来源与覆盖范围</summary>
                    <ul className="mt-2 space-y-2 leading-relaxed">
                      {medicationReviewDraft.sources.map((source) => (
                        <li key={source.source_id}>
                          <span className="font-medium text-foreground">{source.title}</span>（{source.publisher}）<br />
                          定位：{source.locator}；语料校验：{source.content_sha256.slice(0, 12)}…；状态：来源可追溯，待临床治理批准。
                        </li>
                      ))}
                    </ul>
                  </details>
                  <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                    {medicationReviewDraft.disclaimer}
                  </p>
                </div>
              )}
            </div>
          </section>
        )}
      </div>

      {complete && (
        <div className="flex items-start gap-2 rounded-xl border border-primary/30 bg-primary/5 p-4">
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-primary" />
          <p className={cn("leading-relaxed text-foreground", seniorMode ? "text-lg" : "text-sm")}>
            信息已保存。您可以生成带本地证据的待临床复核草案；它不是正式处方或诊断，且不会给出停药、加药或剂量调整指令。
          </p>
        </div>
      )}

      {kind === "prescription" && (
        <section className="space-y-3 rounded-xl border border-primary/30 bg-primary/5 p-4" aria-labelledby="prescription-draft-title">
          <div className="flex items-start gap-3">
            <ClipboardCheck className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
            <div className="min-w-0 space-y-1">
              <h2 id="prescription-draft-title" className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-base")}>
                五大处方待临床复核草案
              </h2>
              <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                系统会检索本地医学知识库并结合您已保存的信息生成草案。每条建议都标有证据编号，药物部分只做核对和监测提示。
              </p>
            </div>
          </div>
          {!complete && (
            <p className={cn("rounded-lg border border-border bg-background p-3 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
              请先填写必填内容并保存，才能生成草案。
            </p>
          )}
          {complete && hasUnsavedChanges && (
            <p className={cn("rounded-lg border border-amber-500/40 bg-amber-50/70 p-3 text-amber-950 dark:bg-amber-950/20 dark:text-amber-100", seniorMode ? "text-lg" : "text-sm")}>
              您修改了信息但尚未保存。请先保存，避免草案遗漏最新内容。
            </p>
          )}
          <Button
            type="button"
            className={actionClass}
            onClick={() => void generateDraft()}
            disabled={!complete || hasUnsavedChanges || saving || documentState !== "idle" || draftState === "generating"}
          >
            {draftState === "generating" ? (
              <span className="codex-activity-dots" aria-hidden="true">
                <span className="codex-activity-dot" />
                <span className="codex-activity-dot" />
                <span className="codex-activity-dot" />
              </span>
            ) : (
              <ClipboardCheck className="size-4" aria-hidden="true" />
            )}
            {draftState === "generating"
              ? `正在检索证据并生成草案 · 已执行 ${formatElapsed(draftElapsedSeconds)}`
              : draft
                ? "重新生成待审核草案"
                : "生成待审核草案"}
          </Button>
        </section>
      )}

      {draft && (
        <section className="space-y-5 rounded-xl border border-primary/35 bg-card p-4 shadow-sm" aria-labelledby="generated-draft-title" aria-live="polite">
          <header className="space-y-2 border-b border-border pb-4">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="generated-draft-title" className={cn("font-semibold text-foreground", seniorMode ? "text-xl" : "text-lg")}>
                五大处方草案
              </h2>
              <span className={cn("rounded-full bg-amber-100 px-2.5 py-1 font-medium text-amber-950 dark:bg-amber-950/40 dark:text-amber-100", seniorMode ? "text-base" : "text-xs")}>
                待临床复核 · 不可自行执行
              </span>
            </div>
            <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
              {draft.health_assessment.summary}
            </p>
            <ul className={cn("list-disc space-y-1 pl-5 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
              {draft.health_assessment.key_issues.map((issue) => <li key={issue}>{issue}</li>)}
            </ul>
          </header>

          <DraftSection section={draft.medication} seniorMode={seniorMode} />
          {draft.medication.medication_items.length > 0 && (
            <DraftList title="已记录的用药信息（需核对）" items={draft.medication.medication_items} seniorMode={seniorMode} />
          )}
          <DraftList title="药物核对与监测重点" items={draft.medication.monitoring_requirements} seniorMode={seniorMode} />
          <DraftSection section={draft.exercise} seniorMode={seniorMode} />
          <DraftList title="不适合运动或需先确认的情况" items={draft.exercise.contraindications} seniorMode={seniorMode} />
          <div className="space-y-2">
            <h3 className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-base")}>运动阶段</h3>
            {draft.exercise.phases.map((phase) => (
              <div key={phase.name} className="rounded-lg border border-border bg-muted/20 p-3">
                <p className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-sm")}>{phase.name} · {phase.duration}</p>
                <p className={cn("mt-1 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>{phase.intensity}</p>
                <p className={cn("mt-1 leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>{phase.instructions}</p>
              </div>
            ))}
          </div>
          <DraftSection section={draft.nutrition} seniorMode={seniorMode} />
          <p className={cn("rounded-lg border border-border bg-muted/20 p-3 leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
            {draft.nutrition.assessment_summary}
            {(draft.nutrition.target_energy_kcal || draft.nutrition.target_protein_g) && " 以下数值仅供医生或营养师核对："}
            {draft.nutrition.target_energy_kcal ? ` 能量 ${draft.nutrition.target_energy_kcal} kcal；` : ""}
            {draft.nutrition.target_protein_g ? ` 蛋白质 ${draft.nutrition.target_protein_g} g。` : ""}
          </p>
          <DraftList title="营养监测重点" items={draft.nutrition.monitoring} seniorMode={seniorMode} />
          <DraftSection section={draft.psychological} seniorMode={seniorMode} />
          <p className={cn("rounded-lg border border-border bg-muted/20 p-3 leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>{draft.psychological.assessment_summary}</p>
          <DraftList title="后续复核" items={[draft.psychological.follow_up]} seniorMode={seniorMode} />
          <DraftSection section={draft.rehabilitation} seniorMode={seniorMode} />
          <DraftList title="训练计划" items={draft.rehabilitation.training_plan} seniorMode={seniorMode} />
          <DraftList title="安全注意事项" items={draft.rehabilitation.safety_precautions} seniorMode={seniorMode} />
          {draft.rehabilitation.assistive_devices.length > 0 && <DraftList title="辅助用具核对" items={draft.rehabilitation.assistive_devices} seniorMode={seniorMode} />}

          <div className="space-y-2 border-t border-border pt-4">
            <h3 className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-base")}>本地医学知识库证据</h3>
            <ul className="space-y-2">
              {draft.evidence_sources.map((source) => (
                <li key={source.evidence_id} className={cn("rounded-lg border border-border bg-muted/20 p-3 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                  <span className="font-medium text-foreground">{source.evidence_id}</span> · {source.title}（{source.locator}）
                </li>
              ))}
            </ul>
            {draft.uploaded_document_ids.length > 0 && (
              <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
                已在本次草案中使用 {draft.uploaded_document_ids.length} 份上传资料作为患者输入；这些资料不是医学知识库证据。
              </p>
            )}
          </div>
          <p className={cn("rounded-lg border border-amber-500/40 bg-amber-50/70 p-3 leading-relaxed text-amber-950 dark:bg-amber-950/20 dark:text-amber-100", seniorMode ? "text-lg" : "text-sm")}>{draft.disclaimer}</p>
        </section>
      )}

      <footer className="flex flex-wrap justify-end gap-3 border-t border-border pt-4">
        <Button variant="outline" className={actionClass} onClick={onExit} disabled={saving}>
          <X className="size-4" />返回咨询
        </Button>
        <Button className={actionClass} onClick={() => void save()} disabled={saving}>
          <Save className="size-4" />{saving ? "正在保存" : "保存信息"}
        </Button>
      </footer>
    </section>
  );
}

function DraftSection({
  section,
  seniorMode,
}: {
  section: FivePrescriptionDraft["medication"] | FivePrescriptionDraft["exercise"] | FivePrescriptionDraft["nutrition"] | FivePrescriptionDraft["psychological"] | FivePrescriptionDraft["rehabilitation"];
  seniorMode: boolean;
}) {
  return (
    <section className="space-y-2">
      <h3 className={cn("font-semibold text-foreground", seniorMode ? "text-xl" : "text-lg")}>{section.title}</h3>
      <p className={cn("leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>{section.goal}</p>
      <ul className={cn("space-y-2", seniorMode ? "text-lg" : "text-sm")}>
        {section.recommendations.map((recommendation) => (
          <li key={`${recommendation.content}-${recommendation.evidence_ids.join("-")}`} className="rounded-lg border border-border bg-muted/20 p-3 leading-relaxed text-foreground">
            {recommendation.content}
            <span className="mt-1 block text-muted-foreground">依据：{recommendation.evidence_ids.join("、")}</span>
          </li>
        ))}
      </ul>
      <DraftList title="注意事项" items={section.precautions} seniorMode={seniorMode} />
    </section>
  );
}

function DraftList({ title, items, seniorMode }: { title: string; items: string[]; seniorMode: boolean }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-1">
      <h4 className={cn("font-medium text-foreground", seniorMode ? "text-lg" : "text-sm")}>{title}</h4>
      <ul className={cn("list-disc space-y-1 pl-5 leading-relaxed text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}
