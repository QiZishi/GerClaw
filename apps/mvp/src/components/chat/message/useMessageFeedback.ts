"use client";

import { useCallback, useEffect, useState } from "react";

import {
  feedbackValueToMessage,
  nextFeedbackValue,
  planMessageFeedbackClick,
  type MessageFeedbackValue,
} from "@/components/chat/message/message-feedback";
import { toast } from "@/components/ui/toast";
import { GerclawApiError } from "@/services/gerclaw/client";
import { createFeedbackIdempotencyKey, submitFeedback } from "@/services/gerclaw/feedback";
import {
  readRunFeedback,
  reconcileRunFeedback,
} from "@/services/gerclaw/runs";
import { useChatStore } from "@/stores/chatStore";
import type { Message } from "@/types";

export function useMessageFeedback(message: Message) {
  const setMessageFeedback = useChatStore((state) => state.setMessageFeedback);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const [feedback, setFeedback] = useState<MessageFeedbackValue>(message.feedback ?? null);
  const [revision, setRevision] = useState(0);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
  const [feedbackType, setFeedbackType] = useState<Exclude<MessageFeedbackValue, null> | null>(null);
  const [feedbackText, setFeedbackText] = useState("");

  const applyFeedback = useCallback((value: -1 | 0 | 1, nextRevision: number) => {
    const visibleValue = feedbackValueToMessage(value);
    setFeedback(visibleValue);
    setRevision(nextRevision);
    setMessageFeedback(message.id, visibleValue);
  }, [message.id, setMessageFeedback]);

  useEffect(() => {
    if (!message.executionRunId) return;
    let active = true;
    void readRunFeedback(message.executionRunId)
      .then((state) => {
        if (!active) return;
        if (state) applyFeedback(state.value, state.revision);
        else applyFeedback(0, 0);
      })
      .catch(() => {
        if (active) toast.show("暂时无法同步这条回答的反馈状态");
      });
    return () => {
      active = false;
    };
  }, [applyFeedback, message.executionRunId]);

  const persistRunFeedbackValue = useCallback(async (desired: -1 | 0 | 1) => {
    if (!message.executionRunId) return null;
    try {
      return await reconcileRunFeedback(message.executionRunId, desired, revision);
    } catch (error) {
      if (!(error instanceof GerclawApiError) || error.status !== 409) throw error;
      const latest = await readRunFeedback(message.executionRunId);
      return reconcileRunFeedback(
        message.executionRunId,
        desired,
        latest?.revision ?? 0,
      );
    }
  }, [message.executionRunId, revision]);

  const reconcile = useCallback(async (
    selected: Exclude<MessageFeedbackValue, null>,
  ) => {
    if (!message.executionRunId || feedbackSubmitting) return;
    const desired = nextFeedbackValue(feedback, selected);
    setFeedbackSubmitting(true);
    try {
      const state = await persistRunFeedbackValue(desired);
      if (!state) return;
      applyFeedback(state.value, state.revision);
      toast.show(state.value === 0 ? "已撤销反馈" : "反馈已更新，感谢您的帮助");
    } catch {
      toast.show("反馈暂未更新，请检查网络后重试");
    } finally {
      setFeedbackSubmitting(false);
    }
  }, [
    applyFeedback,
    feedback,
    feedbackSubmitting,
    message.executionRunId,
    persistRunFeedbackValue,
  ]);

  const handleFeedbackClick = (selected: Exclude<MessageFeedbackValue, null>) => {
    if (feedbackSubmitting) return;
    const action = planMessageFeedbackClick(
      feedback,
      Boolean(message.executionRunId),
      Boolean(message.traceId),
    );
    if (action === "reconcile") {
      void reconcile(selected);
      return;
    }
    if (action !== "open-dialog") return;
    setFeedbackType(selected);
    setFeedbackText("");
    setShowFeedbackDialog(true);
  };

  const dismissFeedbackDialog = () => {
    setShowFeedbackDialog(false);
    setFeedbackText("");
    setFeedbackType(null);
  };

  const submitFeedbackWithComment = async () => {
    if (
      !feedbackType ||
      feedbackSubmitting ||
      (!message.executionRunId && !message.traceId)
    ) return;
    const comment = feedbackText.trim();
    const idempotencyKey = message.traceId
      ? message.feedbackIdempotencyKey ?? createFeedbackIdempotencyKey()
      : undefined;
    if (idempotencyKey) {
      updateMessage(message.id, { feedbackIdempotencyKey: idempotencyKey });
    }
    setFeedbackSubmitting(true);
    let runFeedbackSaved = false;
    try {
      if (message.executionRunId) {
        const desired = feedbackType === "up" ? 1 : -1;
        const state = await persistRunFeedbackValue(desired);
        if (!state) throw new Error("run feedback is unavailable");
        applyFeedback(state.value, state.revision);
        runFeedbackSaved = true;
      }
      if (message.traceId && idempotencyKey) {
        await submitFeedback({
          traceId: message.traceId,
          idempotencyKey,
          rating: feedbackType === "up" ? "positive" : "negative",
          ...(comment ? { comment } : {}),
        });
      }
      if (!message.executionRunId) setFeedback(feedbackType);
      setMessageFeedback(message.id, feedbackType);
      toast.show("反馈已提交，感谢您的帮助");
      dismissFeedbackDialog();
    } catch {
      toast.show(
        runFeedbackSaved && message.traceId
          ? "评分已保存，评价文字暂未提交，请重试"
          : "反馈暂未提交，请检查网络后重试",
      );
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  return {
    feedback,
    feedbackSubmitting,
    feedbackType,
    feedbackText,
    showFeedbackDialog,
    setFeedbackText,
    setShowFeedbackDialog,
    handleFeedbackClick,
    dismissFeedbackDialog,
    submitFeedbackWithComment,
  };
}
