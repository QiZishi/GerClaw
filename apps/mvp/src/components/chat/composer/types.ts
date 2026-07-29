export interface ChatDocumentAttachment {
  localId: string;
  fileName: string;
  mediaType: string;
  source: "mineru" | "local-text";
  markdown: string;
  serverDocumentId?: string;
  documentSessionId?: string;
}

export interface ChatSendAccepted {
  accepted: true;
  documentBindings?: Record<string, string>;
  documentSessionId?: string;
}
