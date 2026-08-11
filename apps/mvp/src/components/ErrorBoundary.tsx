"use client";

import { Component, createRef, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export function ErrorRecoveryView({
  onRetry,
  onReload,
}: {
  onRetry: () => void;
  onReload: () => void;
}) {
  return (
    <main
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
      data-error-recovery-view
      className="flex min-h-screen items-center justify-center bg-background p-4"
    >
      <div className="w-full max-w-md text-center">
        <div className="mx-auto mb-6 flex size-20 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30">
          <AlertTriangle className="size-10 text-amber-600 dark:text-amber-400" aria-hidden />
        </div>
        <h1 className="mb-2 text-2xl font-semibold text-foreground">
          页面出现了一点小问题
        </h1>
        <p className="mb-8 text-base leading-relaxed text-muted-foreground">
          很抱歉，程序遇到了意外错误。您可以尝试重试恢复，或者刷新页面重新开始。
        </p>
        <div className="flex flex-col justify-center gap-3 sm:flex-row">
          <Button
            onClick={onRetry}
            className="min-h-12 gap-2 px-5 text-base"
            size="lg"
          >
            <RefreshCw className="size-4" aria-hidden />
            重试
          </Button>
          <Button
            onClick={onReload}
            variant="outline"
            size="lg"
            className="min-h-12 px-5 text-base"
          >
            刷新页面
          </Button>
        </div>
      </div>
    </main>
  );
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  private fallbackRef = createRef<HTMLDivElement>();

  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    void error;
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    if (process.env.NODE_ENV === "production") {
      console.error("ErrorBoundary caught an unexpected render error");
      return;
    }
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  componentDidUpdate(
    _previousProps: ErrorBoundaryProps,
    previousState: ErrorBoundaryState,
  ) {
    if (!previousState.hasError && this.state.hasError) {
      this.fallbackRef.current?.focus();
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div ref={this.fallbackRef} tabIndex={-1} className="outline-none">
          <ErrorRecoveryView
            onRetry={this.handleRetry}
            onReload={this.handleReload}
          />
        </div>
      );
    }

    return this.props.children;
  }
}
