"use client";

import { useEffect } from "react";

import { ErrorRecoveryView } from "@/components/ErrorBoundary";

export default function RouteError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    if (process.env.NODE_ENV === "production") {
      console.error("A route failed to render", error.digest ?? "no-digest");
      return;
    }
    console.error("A route failed to render", error);
  }, [error]);

  return (
    <ErrorRecoveryView
      onRetry={unstable_retry}
      onReload={() => window.location.reload()}
    />
  );
}
