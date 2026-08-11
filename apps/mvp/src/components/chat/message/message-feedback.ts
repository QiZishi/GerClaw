export type MessageFeedbackValue = "up" | "down" | null;
export type MessageFeedbackClickAction = "open-dialog" | "reconcile" | "ignore";

export function feedbackValueToMessage(value: -1 | 0 | 1): MessageFeedbackValue {
  if (value === 1) return "up";
  if (value === -1) return "down";
  return null;
}

export function nextFeedbackValue(
  current: MessageFeedbackValue,
  selected: Exclude<MessageFeedbackValue, null>,
): -1 | 0 | 1 {
  if (current === selected) return 0;
  return selected === "up" ? 1 : -1;
}

export function planMessageFeedbackClick(
  current: MessageFeedbackValue,
  hasRunFeedback: boolean,
  hasTraceFeedback: boolean,
): MessageFeedbackClickAction {
  if (current !== null) return hasRunFeedback ? "reconcile" : "ignore";
  if (hasTraceFeedback) return "open-dialog";
  return hasRunFeedback ? "reconcile" : "ignore";
}
