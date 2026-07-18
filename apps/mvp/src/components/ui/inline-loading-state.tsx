import { cn } from "@/lib/utils";

interface InlineLoadingStateProps {
  message: string;
  className?: string;
}

/**
 * Calm, shared feedback for bounded fetches. Long-running model work owns its
 * own elapsed-time status and must not use this component as fake progress.
 */
export function InlineLoadingState({ message, className }: InlineLoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex min-h-12 items-center justify-center gap-3 text-muted-foreground", className)}
    >
      <span className="codex-activity-dots" aria-hidden="true">
        <span className="codex-activity-dot" />
        <span className="codex-activity-dot" />
        <span className="codex-activity-dot" />
      </span>
      <span>{message}</span>
    </div>
  );
}
