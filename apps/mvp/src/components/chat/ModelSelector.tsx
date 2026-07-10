"use client";

import { Image as ImageIcon, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";
import { MODEL_OPTIONS, isModelAvailable, type FrontendModelId } from "@/config/models";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";

interface ModelSelectorProps {
  selectedId: FrontendModelId;
  onSelect: (id: FrontendModelId) => void;
  disabled?: boolean;
}

export function ModelSelector({ selectedId, onSelect, disabled }: ModelSelectorProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const selectedOption = MODEL_OPTIONS.find((m) => m.id === selectedId) ?? MODEL_OPTIONS[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "gap-1 h-9 px-2 text-sm font-normal",
              seniorMode && "h-11 px-3 text-base min-w-[44px]"
            )}
            disabled={disabled}
            aria-label="选择模型"
          >
            <span className="truncate max-w-[80px]">{selectedOption.label}</span>
            <ChevronDown className="size-3 shrink-0 opacity-50" />
          </Button>
        }
      />
      <DropdownMenuContent align="end" sideOffset={8} className="w-40">
        <DropdownMenuRadioGroup value={selectedId} onValueChange={(v) => onSelect(v as FrontendModelId)}>
          {MODEL_OPTIONS.map((option) => {
            const available = isModelAvailable(option);
            return (
              <DropdownMenuRadioItem
                key={option.id}
                value={option.id}
                disabled={!available}
                className="flex items-center gap-2"
              >
                <span>{option.label}</span>
                {option.supportsVision && (
                  <ImageIcon className="size-3.5 text-muted-foreground shrink-0" aria-label="支持视觉" />
                )}
              </DropdownMenuRadioItem>
            );
          })}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
