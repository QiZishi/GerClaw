"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Check, History, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { decideMemoryFact, readHealthProfile, readMemoryFactHistory } from "@/services/gerclaw/memory";
import type { HealthProfile, MemoryFact, MemoryFactHistory } from "@/services/gerclaw/schemas";
import { useAppStore } from "@/stores/appStore";

const CATEGORY_LABELS: Record<MemoryFact["category"], string> = {
  basic_info: "基本资料",
  allergy: "过敏史",
  condition: "病史与慢病",
  medication: "用药情况",
  vital_sign: "生命体征",
  assessment: "评估记录",
  event: "重要健康事件",
  social: "照护与社会支持",
  preference: "照护偏好",
  goal: "健康目标",
};

type LoadState = "loading" | "ready" | "error";

export function HealthProfilePanel() {
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const isSeniorPatient = role === "patient" && seniorMode;
  const [profile, setProfile] = useState<HealthProfile | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [decidingFactId, setDecidingFactId] = useState<string | null>(null);
  const [historyFactId, setHistoryFactId] = useState<string | null>(null);
  const [factHistory, setFactHistory] = useState<MemoryFactHistory | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const requestIdRef = useRef(0);
  const historyRequestIdRef = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoadState("loading");
    setError(null);
    try {
      const nextProfile = await readHealthProfile();
      if (requestId !== requestIdRef.current) return;
      setProfile(nextProfile);
      setLoadState("ready");
    } catch (requestError) {
      if (requestId !== requestIdRef.current) return;
      setLoadState("error");
      setError(requestError instanceof Error ? requestError.message : "健康记录暂时无法读取");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => {
      window.clearTimeout(timer);
      requestIdRef.current += 1;
    };
  }, [refresh]);

  const confirmedSections = useMemo(() => {
    const sections = new Map<MemoryFact["category"], MemoryFact[]>();
    for (const fact of profile?.facts ?? []) {
      if (fact.status !== "confirmed") continue;
      sections.set(fact.category, [...(sections.get(fact.category) ?? []), fact]);
    }
    return [...sections.entries()];
  }, [profile]);
  const pendingFacts = useMemo(
    () => (profile?.facts ?? []).filter((fact) => fact.status === "pending"),
    [profile]
  );

  const handleDecision = useCallback(
    async (fact: MemoryFact, decision: "confirm" | "reject") => {
      setDecidingFactId(fact.id);
      try {
        await decideMemoryFact(fact.id, fact.revision, decision);
        historyRequestIdRef.current += 1;
        setHistoryFactId(null);
        setFactHistory(null);
        setHistoryError(null);
        toast.show(decision === "confirm" ? "已确认并更新健康记录" : "已忽略这条待确认信息");
        await refresh();
      } catch (decisionError) {
        toast.show(
          decisionError instanceof Error ? decisionError.message : "操作未完成，请刷新后重试"
        );
      } finally {
        setDecidingFactId(null);
      }
    },
    [refresh]
  );

  const loadFactHistory = useCallback(async (fact: MemoryFact) => {
      const requestId = ++historyRequestIdRef.current;
      setHistoryFactId(fact.id);
      setFactHistory(null);
      setHistoryError(null);
      setHistoryLoading(true);
      try {
        const history = await readMemoryFactHistory(fact.id);
        if (requestId !== historyRequestIdRef.current) return;
        setFactHistory(history);
      } catch (historyRequestError) {
        if (requestId !== historyRequestIdRef.current) return;
        setHistoryError(
          historyRequestError instanceof Error
            ? historyRequestError.message
            : "变更历史暂时无法读取，请稍后重试。"
        );
      } finally {
        if (requestId === historyRequestIdRef.current) setHistoryLoading(false);
      }
    }, []);

  const toggleFactHistory = useCallback(
    (fact: MemoryFact) => {
      if (historyFactId === fact.id) {
        historyRequestIdRef.current += 1;
        setHistoryFactId(null);
        setFactHistory(null);
        setHistoryError(null);
        setHistoryLoading(false);
        return;
      }
      void loadFactHistory(fact);
    },
    [historyFactId, loadFactHistory]
  );

  const bodyClassName = cn("text-sm leading-6", isSeniorPatient && "text-lg leading-8");
  const actionClassName = cn(isSeniorPatient && "min-h-12 px-3 text-base");

  if (loadState === "loading" && !profile) {
    return (
      <PanelStatus
        className={bodyClassName}
        title="正在读取您的健康记录"
        description="请稍候，页面会在读取完成后更新。"
      />
    );
  }

  if (loadState === "error" && !profile) {
    return (
      <PanelStatus
        className={bodyClassName}
        title="健康记录暂时无法读取"
        description={error ?? "请检查网络后重试。"}
        action={
          <Button type="button" variant="outline" className={actionClassName} onClick={() => void refresh()}>
            <RefreshCw className="size-4" />
            重新读取
          </Button>
        }
      />
    );
  }

  return (
    <div className={cn("flex-1 overflow-y-auto p-4", isSeniorPatient && "p-5")}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className={cn("font-semibold", isSeniorPatient && "text-xl")}>我的健康记录</h2>
          <p className={cn("mt-1 text-muted-foreground", bodyClassName)}>
            仅显示您已确认的个人自述信息，不构成诊断或治疗建议。
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size={isSeniorPatient ? "default" : "sm"}
          className={cn("shrink-0", actionClassName)}
          onClick={() => void refresh()}
          disabled={loadState === "loading" || decidingFactId !== null}
        >
          <RefreshCw className="size-4" />
          刷新
        </Button>
      </div>

      {loadState === "loading" && (
        <p className={cn("mb-3 text-muted-foreground", bodyClassName)} role="status" aria-live="polite">
          正在刷新健康记录…
        </p>
      )}
      {loadState === "error" && (
        <p className={cn("mb-3 text-destructive", bodyClassName)} role="status">
          {error ?? "刷新未完成，正在显示上次读取的内容。"}
        </p>
      )}

      {confirmedSections.length === 0 && pendingFacts.length === 0 ? (
        <PanelStatus
          className={bodyClassName}
          title="还没有已确认的健康记录"
          description="您在对话中确认的信息会显示在这里。系统不会用示例资料代替您的记录。"
        />
      ) : (
        <div className="space-y-4">
          {confirmedSections.map(([category, facts]) => (
            <section key={category} aria-labelledby={`health-section-${category}`}>
              <h3 id={`health-section-${category}`} className={cn("mb-2 font-medium", isSeniorPatient && "text-lg")}>
                {CATEGORY_LABELS[category]}
              </h3>
              <ul className="space-y-2">
                {facts.map((fact) => {
                  const isHistoryOpen = historyFactId === fact.id;
                  return (
                    <li key={fact.id} className={cn("rounded-lg border border-border bg-card p-3", bodyClassName)}>
                      <p>{fact.statement}</p>
                      <Button
                        type="button"
                        variant="ghost"
                        size={isSeniorPatient ? "default" : "sm"}
                        className={cn("mt-2", actionClassName)}
                        disabled={decidingFactId !== null}
                        aria-expanded={isHistoryOpen}
                        onClick={() => void toggleFactHistory(fact)}
                      >
                        <History className="size-4" />
                        {isHistoryOpen ? "收起变更历史" : "查看变更历史"}
                      </Button>
                      {isHistoryOpen && (
                        <FactHistory
                          history={factHistory}
                          loading={historyLoading}
                          error={historyError}
                          className={bodyClassName}
                          actionClassName={actionClassName}
                          onRetry={() => void loadFactHistory(fact)}
                        />
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}

          {pendingFacts.length > 0 && (
            <section aria-labelledby="health-pending-facts">
              <h3 id="health-pending-facts" className={cn("mb-1 font-medium", isSeniorPatient && "text-lg")}>
                待您确认的信息
              </h3>
              <p className={cn("mb-2 text-muted-foreground", bodyClassName)}>
                请核对是否准确；确认后才会作为您的健康记录保存。
              </p>
              <ul className="space-y-3">
                {pendingFacts.map((fact) => {
                  const isDeciding = decidingFactId === fact.id;
                  return (
                    <li key={fact.id} className={cn("rounded-lg border border-primary/30 bg-primary/5 p-3", bodyClassName)}>
                      <p>{fact.statement}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                          type="button"
                          size={isSeniorPatient ? "default" : "sm"}
                          className={actionClassName}
                          disabled={decidingFactId !== null}
                          onClick={() => void handleDecision(fact, "confirm")}
                        >
                          <Check className="size-4" />
                          {isDeciding ? "正在保存" : "确认准确"}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size={isSeniorPatient ? "default" : "sm"}
                          className={actionClassName}
                          disabled={decidingFactId !== null}
                          onClick={() => void handleDecision(fact, "reject")}
                        >
                          <X className="size-4" />
                          忽略此条
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function FactHistory({
  history,
  loading,
  error,
  className,
  actionClassName,
  onRetry,
}: {
  history: MemoryFactHistory | null;
  loading: boolean;
  error: string | null;
  className: string;
  actionClassName: string;
  onRetry: () => void;
}) {
  if (loading) {
    return (
      <p className={cn("mt-3 text-muted-foreground", className)} role="status" aria-live="polite">
        正在读取这条记录的变更历史…
      </p>
    );
  }
  if (error) {
    return (
      <div className={cn("mt-3 rounded-md bg-destructive/10 p-3", className)} role="status">
        <p>{error}</p>
        <Button type="button" variant="outline" size="sm" className={cn("mt-2", actionClassName)} onClick={onRetry}>
          重新读取历史
        </Button>
      </div>
    );
  }
  if (!history || history.items.length === 0) {
    return <p className={cn("mt-3 text-muted-foreground", className)}>这条记录尚无历史版本。</p>;
  }
  return (
    <div className={cn("mt-3 border-t border-border pt-3", className)}>
      <p className="text-muted-foreground">仅显示您本人这条记录此前保存的版本。</p>
      <ol className="mt-2 space-y-2">
        {history.items.map((item) => (
          <li key={`${item.revision}-${item.recorded_at}`} className="rounded-md bg-muted/50 p-2">
            <p className="font-medium">版本 {item.revision}</p>
            <p className="mt-1">{item.statement}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function PanelStatus({
  title,
  description,
  className,
  action,
}: {
  title: string;
  description: string;
  className: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <p className={cn("font-medium", className)} role="status" aria-live="polite">
        {title}
      </p>
      <p className={cn("max-w-sm text-muted-foreground", className)}>{description}</p>
      {action}
    </div>
  );
}
