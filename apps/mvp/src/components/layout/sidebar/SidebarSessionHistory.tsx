"use client";

import { useMemo, useState } from "react";
import { Pencil, Pin, Search, Trash2 } from "lucide-react";

import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  formatRelativeTime,
  groupByTime,
  type SessionGroup,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

interface SidebarSessionHistoryProps {
  sessions: Session[];
  currentSessionId: string | null;
  mounted: boolean;
  seniorMode: boolean;
  isDoctor: boolean;
  isPatient: boolean;
  patientHistoryOpen: boolean;
  onSelect: (sessionId: string) => void;
  onRename: (session: Session) => void;
  onDelete: (session: Session) => void;
  onTogglePin: (sessionId: string) => void;
}

export function SidebarSessionHistory({
  sessions,
  currentSessionId,
  mounted,
  seniorMode,
  isDoctor,
  isPatient,
  patientHistoryOpen,
  onSelect,
  onRename,
  onDelete,
  onTogglePin,
}: SidebarSessionHistoryProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const visible = !isPatient || patientHistoryOpen;
  const groupedSessions = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    const filtered = sessions.filter(
      (session) =>
        !normalizedQuery ||
        session.title.toLowerCase().includes(normalizedQuery),
    );
    const groups: Record<SessionGroup, Session[]> = {
      今天: [],
      昨天: [],
      最近7天: [],
      更早: [],
    };
    for (const session of filtered) {
      groups[groupByTime(session.updatedAt)].push(session);
    }
    for (const group of Object.keys(groups) as SessionGroup[]) {
      groups[group].sort((left, right) => {
        if (Boolean(left.pinned) !== Boolean(right.pinned)) {
          return left.pinned ? -1 : 1;
        }
        return right.updatedAt - left.updatedAt;
      });
    }
    return groups;
  }, [searchQuery, sessions]);

  if (!visible) return <div className="flex-1" />;
  return (
    <>
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder={isDoctor ? "搜索病例会话" : "搜索对话记录"}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className={cn(
              "h-8 pl-8",
              seniorMode && "h-12 pl-10 text-lg",
            )}
          />
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="px-2 py-1">
          {!mounted ? (
            <div
              className={cn(
                "px-2 py-4 text-center text-sm text-muted-foreground",
                seniorMode && "text-lg",
              )}
            >
              加载中...
            </div>
          ) : sessions.length === 0 ? (
            <div className="px-3 py-7 text-center">
              <p
                className={cn(
                  "text-sm font-medium",
                  seniorMode && "text-lg",
                )}
              >
                {isDoctor ? "还没有病例会话" : "还没有对话记录"}
              </p>
            </div>
          ) : (
            (Object.keys(groupedSessions) as SessionGroup[]).map((group) => {
              const groupSessions = groupedSessions[group];
              if (groupSessions.length === 0) return null;
              return (
                <div key={group} className="mb-2">
                  <div
                    className={cn(
                      "px-2 py-1 text-xs font-medium text-muted-foreground",
                      seniorMode && "text-base",
                    )}
                  >
                    {group}
                  </div>
                  {groupSessions.map((session) => (
                    <SidebarSessionItem
                      key={session.id}
                      session={session}
                      active={currentSessionId === session.id}
                      seniorMode={seniorMode}
                      onSelect={() => onSelect(session.id)}
                      onRename={() => onRename(session)}
                      onDelete={() => onDelete(session)}
                      onTogglePin={() => onTogglePin(session.id)}
                    />
                  ))}
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>
    </>
  );
}

function SidebarSessionItem({
  session,
  active,
  seniorMode,
  onSelect,
  onRename,
  onDelete,
  onTogglePin,
}: {
  session: Session;
  active: boolean;
  seniorMode: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
  onTogglePin: () => void;
}) {
  const actionClass = cn(
    "rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-background hover:text-foreground",
    seniorMode &&
      "inline-flex min-h-12 min-w-0 flex-col justify-center gap-0.5 whitespace-normal px-1 text-lg leading-tight",
  );
  return (
    <div
      data-session-item
      className={cn(
        "group relative mx-0.5 flex items-center gap-2 rounded-xl px-2 py-2.5 transition-colors duration-150 ease-out",
        seniorMode && "flex-col items-stretch px-3 py-3",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "hover:bg-sidebar-accent/70",
      )}
    >
      <div
        className={cn(
          "absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-full bg-primary transition-opacity",
          active ? "opacity-100" : "opacity-0",
        )}
      />
      <button
        type="button"
        className={cn(
          "ml-1 min-w-0 flex-1 text-left",
          seniorMode && "min-h-12",
        )}
        onClick={onSelect}
      >
        <div className="flex items-center gap-1">
          {session.pinned && (
            <Pin className="size-3 shrink-0 text-primary" />
          )}
          <div className={cn("truncate text-sm font-medium", seniorMode && "text-lg")}>
            {session.title}
          </div>
        </div>
        <div className={cn("mt-0.5 truncate text-xs text-muted-foreground", seniorMode && "text-base")}>
          {session.lastMessagePreview ?? formatRelativeTime(session.updatedAt)}
        </div>
      </button>
      <div
        className={cn(
          "flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100",
          seniorMode && "grid w-full grid-cols-3 gap-1.5 opacity-100",
        )}
      >
        <button type="button" className={actionClass} onClick={onRename} aria-label="重命名">
          <Pencil className="size-3.5" />
          {seniorMode && <span>重命名</span>}
        </button>
        <button
          type="button"
          className={actionClass}
          onClick={onTogglePin}
          aria-label={session.pinned ? "取消置顶" : "置顶"}
        >
          <Pin className="size-3.5" />
          {seniorMode && <span>{session.pinned ? "取消置顶" : "置顶"}</span>}
        </button>
        <button
          type="button"
          className={cn(actionClass, "hover:text-destructive")}
          onClick={onDelete}
          aria-label="删除"
        >
          <Trash2 className="size-3.5" />
          {seniorMode && <span>删除</span>}
        </button>
      </div>
    </div>
  );
}
