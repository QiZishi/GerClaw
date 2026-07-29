"use client";

import Image from "next/image";
import { X } from "lucide-react";

import { DocumentToolCard } from "@/components/document/DocumentToolCard";
import { FileTag } from "@/components/document/FileTag";
import { SkillTag } from "@/components/skills/SkillTag";
import { cn } from "@/lib/utils";
import type { FileTag as UploadFileTag } from "@/types";
import type { SkillInfo } from "@/services/gerclaw/schemas";

export interface PendingComposerImage {
  id: string;
  mimeType: string;
  base64: string;
  previewUrl: string;
  alt?: string;
}

interface ComposerAttachmentTrayProps {
  documents: UploadFileTag[];
  images: PendingComposerImage[];
  loadedSkillIds: string[];
  availableSkills: SkillInfo[];
  seniorMode: boolean;
  onCancelDocument: (id: string) => void;
  onRetryDocument: (id: string) => void;
  onRemoveDocument: (id: string) => void;
  onRemoveImage: (id: string) => void;
  onRemoveSkill: (id: string) => void;
}

export function ComposerAttachmentTray({
  documents,
  images,
  loadedSkillIds,
  availableSkills,
  seniorMode,
  onCancelDocument,
  onRetryDocument,
  onRemoveDocument,
  onRemoveImage,
  onRemoveSkill,
}: ComposerAttachmentTrayProps) {
  if (documents.length === 0 && images.length === 0 && loadedSkillIds.length === 0) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {documents.map((file) => (
        <div key={file.id} className="min-w-0 space-y-2">
          {file.status === "done" ? (
            <DocumentToolCard data={file} onRemove={onRemoveDocument} />
          ) : (
            <FileTag
              data={file}
              onRetry={file.status === "failed" ? onRetryDocument : undefined}
              onCancel={file.status === "parsing" ? onCancelDocument : undefined}
              onRemove={file.status === "failed" ? onRemoveDocument : undefined}
            />
          )}
        </div>
      ))}
      {images.map((image) => (
        <div key={image.id} className={cn("relative group", seniorMode ? "w-32" : "size-16")}>
          <div className="relative size-16">
            <Image
              src={image.previewUrl}
              alt={image.alt ?? "上传图片"}
              fill
              sizes="64px"
              unoptimized
              className="rounded-md border border-border object-cover"
            />
          </div>
          <button
            type="button"
            onClick={() => onRemoveImage(image.id)}
            className={cn(
              "absolute -right-1.5 -top-1.5 flex size-5 items-center justify-center rounded-full bg-destructive text-destructive-foreground opacity-0 shadow transition-opacity group-hover:opacity-100",
              seniorMode && "static mt-1 min-h-12 w-full gap-1 rounded-md px-2 text-base opacity-100",
            )}
            aria-label={`移除图片 ${image.alt ?? ""}`.trim()}
          >
            <X className="size-3" aria-hidden />
            {seniorMode && <span>移除图片</span>}
          </button>
        </div>
      ))}
      {loadedSkillIds.map((id) => (
        <SkillTag
          key={id}
          skill={
            availableSkills.find((skill) => skill.skill_id === id) ?? {
              skill_id: id,
              name: "正在读取技能",
              source: "builtin",
            }
          }
          removable
          onRemove={onRemoveSkill}
          className={cn(seniorMode && "min-h-12 px-3 text-lg")}
        />
      ))}
    </div>
  );
}
