type BackendSessionPresentation = {
  id: string;
  title: string | null;
  has_prescription_draft: boolean;
  created_at: string;
  updated_at: string;
};

type FrontendSessionPresentation = {
  id: string;
  title: string;
  role: "patient" | "doctor" | "admin";
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  panelType?: "prescription";
};

/** Converts owner-visible session metadata into a presentation-only session. */
export function toFrontendSession(
  item: BackendSessionPresentation,
  role: "patient" | "doctor" | "admin",
): FrontendSessionPresentation {
  return {
    id: item.id,
    title: item.has_prescription_draft ? "五大处方计划" : item.title ?? "新对话",
    role,
    createdAt: Date.parse(item.created_at),
    updatedAt: Date.parse(item.updated_at),
    messageCount: 0,
    ...(item.has_prescription_draft ? { panelType: "prescription" as const } : {}),
  };
}
