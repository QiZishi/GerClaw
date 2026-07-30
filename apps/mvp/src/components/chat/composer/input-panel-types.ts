import type {
  ChangeEventHandler,
  KeyboardEventHandler,
} from "react";

import type { ComposerAction } from "@/components/chat/composer/ComposerToolbar";
import type { PendingComposerImage } from "@/components/chat/composer/ComposerAttachmentTray";
import type { SkillInfo } from "@/services/gerclaw/schemas";
import type { FileTag as UploadFileTag, Role } from "@/types";

export interface ComposerInputPanelProps {
  text: string;
  placeholder: string;
  role: Role;
  seniorMode: boolean;
  mounted: boolean;
  isGuest: boolean;
  isOnline: boolean;
  asrAvailable: boolean;
  isGenerating: boolean;
  isSending: boolean;
  directiveSubmitting: "queue" | "steer" | null;
  isTranscribing: boolean;
  contextLoading: boolean;
  companionMode: boolean;
  prescriptionConversation: boolean;
  micDisabled: boolean;
  dragActive: boolean;
  hasUnboundParsedDocuments: boolean;
  pendingImages: PendingComposerImage[];
  pendingDocuments: UploadFileTag[];
  loadedSkillIds: string[];
  availableSkills: SkillInfo[];
  selectedCapabilityIds: string[];
  limitDialogMessage: string | null;
  bindTextarea: (element: HTMLTextAreaElement | null) => void;
  bindImageInput: (element: HTMLInputElement | null) => void;
  bindFileInput: (element: HTMLInputElement | null) => void;
  onPickImage: () => void;
  onPickFile: () => void;
  onInput: ChangeEventHandler<HTMLTextAreaElement>;
  onKeyDown: KeyboardEventHandler<HTMLTextAreaElement>;
  onPasteFiles: (files: File[]) => void;
  onAddImages: (files: File[]) => void;
  onAddFiles: (files: File[]) => void;
  onDragActiveChange: (active: boolean) => void;
  onCancelDocument: (id: string) => void;
  onRetryDocument: (id: string) => void;
  onRemoveDocument: (id: string) => void;
  onRemoveImage: (id: string) => void;
  onRemoveSkill: (id: string) => void;
  onCapabilityChange: (ids: string[]) => void;
  onAction: (action: ComposerAction) => void;
  onSend: () => void;
  onStop?: () => void;
  onQueue: () => void;
  onSteer: () => void;
  onMicStart: () => void;
  onCancelTranscription: () => void;
  onLimitDialogChange: (message: string | null) => void;
}
