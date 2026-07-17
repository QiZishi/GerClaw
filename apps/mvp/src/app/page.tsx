"use client";

import { useEffect, useState } from "react";
import { Menu, PanelLeftClose, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Sidebar } from "@/components/layout/Sidebar";
import { ChatArea } from "@/components/layout/ChatArea";
import { DoctorHome } from "@/components/layout/DoctorHome";
import { RightPanel } from "@/components/layout/RightPanel";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import { cn } from "@/lib/utils";
import { AdminDashboard } from "@/components/account/AdminDashboard";
import { getAccountIdentity, type AccountIdentity } from "@/services/account";
import { LoginPage } from "@/components/account/LoginPage";

/**
 * 角色路由分发
 * 静态导出无服务端路由，用条件渲染：role=doctor 显示医生端，否则患者端
 * - 患者端：Sidebar + ChatArea + RightPanel
 * - 医生端：Sidebar + DoctorHome（无会话显示医生首页，有会话进入 ChatArea） + RightPanel
 *
 * 侧边栏折叠时不渲染 Sidebar，改在中间主视图左上角浮动显示"展开按钮 + 新建对话按钮"
 */
export default function Home() {
  const role = useAppStore((s) => s.role);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const mobileSidebarOpen = useAppStore((s) => s.mobileSidebarOpen);
  const setMobileSidebarOpen = useAppStore((s) => s.setMobileSidebarOpen);
  const setRole = useAppStore((s) => s.setRole);
  const setGuestMode = useAppStore((s) => s.setGuestMode);
  const createSession = useChatStore((s) => s.createSession);
  const setCurrentSession = useAppStore((s) => s.setCurrentSession);
  const isSeniorPatient = role === "patient" && seniorMode;
  const [identity, setIdentity] = useState<AccountIdentity | null | undefined>(undefined);
  const [guestEntry, setGuestEntry] = useState(false);
  useEffect(() => { void getAccountIdentity().then(setIdentity); }, []);
  useEffect(() => {
    if (!identity) return;
    // Never render browser-local drafts from a prior person under a newly
    // verified account. Durable records remain owner-scoped in the API.
    useChatStore.getState().clearAllData();
    setGuestMode(false);
    setRole(identity.role);
  }, [identity, setGuestMode, setRole]);
  useEffect(() => {
    if (guestEntry) useChatStore.getState().clearAllData();
  }, [guestEntry]);

  // Sheet 内容通过 Portal 渲染；跨过宽桌面断点时必须主动关闭，
  // 否则旧的遮罩会停留在页面上并遮挡桌面布局。
  useEffect(() => {
    const closeDrawerOnWideViewport = () => {
      if (window.innerWidth >= 1280) {
        setMobileSidebarOpen(false);
      }
    };

    closeDrawerOnWideViewport();
    window.addEventListener("resize", closeDrawerOnWideViewport);
    return () => window.removeEventListener("resize", closeDrawerOnWideViewport);
  }, [setMobileSidebarOpen]);

  if (identity === undefined) return <div className="grid min-h-screen place-items-center text-muted-foreground" role="status">正在准备登录…</div>;
  if (!identity && !guestEntry) return <LoginPage onAuthenticated={(account) => { useChatStore.getState().clearAllData(); setGuestMode(false); setIdentity(account); }} onGuest={() => { useChatStore.getState().clearAllData(); setGuestMode(true); setRole("patient"); setGuestEntry(true); }} />;

  const handleQuickNew = () => {
    const id = createSession(role);
    setCurrentSession(id);
  };

  if (role === "admin") return <AdminDashboard />;

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background relative">
      {/* 宽桌面侧边栏（窄桌面与平板改用抽屉，优先保留聊天区宽度）*/}
      {!sidebarCollapsed && (
        <div className="hidden xl:flex h-full">
          <Sidebar />
        </div>
      )}

      {/* 折叠时浮动顶栏：展开按钮 + 新建对话按钮（左上角并排）*/}
      {sidebarCollapsed && (
        <div className="hidden xl:flex absolute top-2 left-2 z-30 items-center gap-1">
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size={isSeniorPatient ? "default" : "icon"}
                  className={cn(
                    "btn-icon",
                    isSeniorPatient && "min-h-12 gap-2 px-3 text-base"
                  )}
                  onClick={toggleSidebar}
                  aria-label="展开侧边栏"
                />
              }
            >
              <PanelLeftClose className="size-4" />
              {isSeniorPatient && <span>展开</span>}
            </TooltipTrigger>
            <TooltipContent side="bottom">展开侧边栏</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size={isSeniorPatient ? "default" : "icon"}
                  className={cn(
                    "btn-icon text-foreground hover:text-foreground",
                    isSeniorPatient && "min-h-12 gap-2 px-3 text-base"
                  )}
                  onClick={handleQuickNew}
                  aria-label="新建对话"
                />
              }
            >
              <Plus className="size-4" />
              {isSeniorPatient && <span>新建</span>}
            </TooltipTrigger>
            <TooltipContent side="bottom">新建对话</TooltipContent>
          </Tooltip>
        </div>
      )}

      {/* 窄屏侧边栏（Sheet 抽屉）*/}
      <div className="xl:hidden">
        <Sheet
          open={mobileSidebarOpen}
          onOpenChange={setMobileSidebarOpen}
        >
          <SheetTrigger
            render={
              <Button
                variant="ghost"
                size="default"
                className="btn-icon absolute top-2 left-2 z-20 min-h-12 gap-2 bg-background/95 px-3 text-base shadow-sm xl:hidden"
                aria-label="打开菜单"
              />
            }
          >
            <Menu className="size-4" />
            <span>菜单</span>
          </SheetTrigger>
          <SheetContent
            side="left"
            className="p-0"
            style={{ width: isSeniorPatient ? "min(92vw, 360px)" : "280px" }}
            showCloseButton={false}
          >
            <Sidebar onNavigate={() => setMobileSidebarOpen(false)} />
          </SheetContent>
        </Sheet>
      </div>

      {/* 中间主视图：医生端用 DoctorHome，患者端用 ChatArea */}
      {role === "doctor" ? <DoctorHome /> : <ChatArea />}

      {/* 右侧动态面板 */}
      <RightPanel />
    </div>
  );
}
