import type {
  AgentRun,
  RunEventPage,
} from "./run-contract";

export type ConversationRecoveryPlan =
  | {
      action: "stream";
      mode: "attach" | "resume";
      afterSequence: number;
      publicSummaries: string[];
    }
  | { action: "refresh-history" };

function publicSummaries(replay: RunEventPage): string[] {
  return Array.from(
    new Set(
      replay.events
        .map((event) => event.public_summary)
        .filter((summary): summary is string => Boolean(summary))
    )
  ).slice(-20);
}

/**
 * History hydration has not rendered any RunEvent. A still-running Run must
 * therefore replay from sequence zero so a completion racing the refresh
 * cannot leave the client subscribed after its terminal event.
 */
export function planConversationRecovery(
  run: AgentRun,
  replay?: RunEventPage
): ConversationRecoveryPlan {
  if (run.status === "running") {
    return {
      action: "stream",
      mode: "attach",
      afterSequence: 0,
      publicSummaries: [],
    };
  }
  if (run.status === "interrupted") {
    return {
      action: "stream",
      mode: "resume",
      afterSequence: 0,
      publicSummaries: replay ? publicSummaries(replay) : [],
    };
  }
  return { action: "refresh-history" };
}
