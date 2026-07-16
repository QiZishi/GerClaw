"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, FileText, LoaderCircle, Paperclip, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";
import { GerclawApiError } from "@/services/gerclaw/client";
import {
  getClinicalIntake,
  startClinicalIntake,
  updateClinicalIntake,
  type ClinicalIntakeKind,
} from "@/services/gerclaw/clinical-intakes";
import type { ClinicalIntake } from "@/services/gerclaw/schemas";
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
}

export function ClinicalIntakeForm({
  localSessionId,
  kind,
  seniorMode,
  onExit,
}: ClinicalIntakeFormProps) {
  const [intake, setIntake] = useState<ClinicalIntake | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [saving, setSaving] = useState(false);
  const [documentState, setDocumentState] = useState<"idle" | "parsing" | "saving">("idle");
  const [documentNames, setDocumentNames] = useState<Record<string, string>>({});
  const [reloadNonce, setReloadNonce] = useState(0);
  const [showValidation, setShowValidation] = useState(false);
  const fieldRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});
  const documentInputRef = useRef<HTMLInputElement>(null);
  const pendingStartRef = useRef<{
    key: string;
    promise: Promise<ClinicalIntake>;
  } | null>(null);

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
      toast.show(
        next.status === "information_complete_pending_governance"
          ? "信息已安全保存；当前不会生成医疗建议"
          : "信息已保存，您可以继续补充"
      );
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "信息暂未保存，请检查网络后重试");
    } finally {
      setSaving(false);
    }
  };

  const updateDocumentReferences = async (documentIds: string[]) => {
    if (!intake || saving || documentState !== "idle") return;
    setDocumentState("saving");
    try {
      const next = await updateClinicalIntake({
        intakeId: intake.intake_id,
        expectedRevision: intake.revision,
        answers: {},
        documentIds,
      });
      setIntake(next);
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "资料关联暂未保存，请重试");
    } finally {
      setDocumentState("idle");
    }
  };

  const attachDocument = async (file: File | undefined) => {
    if (!file || !intake || saving || documentState !== "idle") return;
    const mediaType = documentMediaType(file);
    if (!mediaType) {
      toast.show("仅支持 PDF、Word、Markdown 或文本资料");
      return;
    }
    setDocumentState("parsing");
    let registeredDocumentId: string | null = null;
    try {
      const parsed = await parseFile(file);
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
                  PDF、Word、Markdown 或文本会先由 MinerU 提取文本，作为本次五大处方信息收集的输入。未来经审核的报告会将其标为“上传资料依据”，不会把它当作本地医学知识库证据。
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
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Paperclip className="size-4" aria-hidden="true" />
                )}
                {documentState === "parsing" ? "正在用 MinerU 解析" : documentState === "saving" ? "正在保存资料" : "上传补充资料"}
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
      </div>

      {complete && (
        <div className="flex items-start gap-2 rounded-xl border border-primary/30 bg-primary/5 p-4">
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-primary" />
          <p className={cn("leading-relaxed text-foreground", seniorMode ? "text-lg" : "text-sm")}>
            信息已保存。医学规则、医生审核和患者授权尚未启用，因此不会提供处方、停药、加药或剂量调整建议。
          </p>
        </div>
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
