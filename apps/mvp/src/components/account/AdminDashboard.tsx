"use client";

import { useEffect, useState } from "react";
import { ArrowLeftRight, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { switchAdministratorView } from "@/services/account";

type Account = { actor_id: string; username: string; role: "patient" | "doctor" | "admin"; is_active: boolean; created_at: string };

export function AdminDashboard() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = async () => { setLoading(true); setError(null); try { const response = await fetch("/api/account/admin/accounts", { cache: "no-store" }); const body = await response.json(); if (!response.ok) throw new Error(); setAccounts(body.accounts); } catch { setError("暂时无法读取账户目录。"); } finally { setLoading(false); } };
  useEffect(() => {
    void fetch("/api/account/admin/accounts", { cache: "no-store" })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error();
        setAccounts(body.accounts);
      })
      .catch(() => setError("暂时无法读取账户目录。"))
      .finally(() => setLoading(false));
  }, []);
  const change = async (actorId: string, patch: Partial<Pick<Account, "role" | "is_active">>) => { const csrf = document.cookie.split("; ").find((value) => value.startsWith("gerclaw_account_csrf="))?.split("=")[1]; const response = await fetch(`/api/account/admin/accounts/${actorId}`, { method: "PATCH", headers: { "content-type": "application/json", "x-gerclaw-csrf": csrf ?? "" }, body: JSON.stringify(patch) }); if (!response.ok) { setError("账户更新未完成。"); return; } const item = await response.json(); setAccounts((items) => items.map((account) => account.actor_id === actorId ? item : account)); };
  const switchView = async (role: "patient" | "doctor") => { await switchAdministratorView(role); window.location.assign("/"); };
  return <main className="min-h-screen bg-background p-4 sm:p-8"><section className="mx-auto max-w-5xl"><header className="mb-7 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><div className="grid size-11 place-items-center rounded-xl bg-primary text-primary-foreground"><ShieldCheck /></div><div><h1 className="text-2xl font-semibold">账户管理</h1><p className="text-sm text-muted-foreground">管理账户状态与工作区身份</p></div></div><div className="flex gap-2"><Button variant="outline" onClick={() => void switchView("patient")}><ArrowLeftRight />患者端</Button><Button variant="outline" onClick={() => void switchView("doctor")}><ArrowLeftRight />医生端</Button><Button variant="outline" onClick={() => void load()} disabled={loading}><RefreshCw className={loading ? "animate-spin" : ""} />刷新</Button></div></header>{error && <p role="alert" className="mb-3 rounded-lg bg-destructive/10 p-3 text-destructive">{error}</p>}<div className="overflow-hidden rounded-xl border"><table className="w-full text-left text-sm"><thead className="bg-muted/50 text-muted-foreground"><tr><th className="p-3">账号</th><th className="p-3">身份</th><th className="p-3">状态</th><th className="p-3">操作</th></tr></thead><tbody>{accounts.map((account) => <tr key={account.actor_id} className="border-t"><td className="p-3 font-medium">{account.username}</td><td className="p-3"><select aria-label={`${account.username}身份`} value={account.role} disabled={account.role === "admin"} onChange={(event) => void change(account.actor_id, { role: event.target.value as "patient" | "doctor" })}><option value="patient">患者</option><option value="doctor">医生</option><option value="admin">管理员</option></select></td><td className="p-3">{account.is_active ? "正常" : "已停用"}</td><td className="p-3"><Button size="sm" variant="outline" disabled={account.role === "admin"} onClick={() => void change(account.actor_id, { is_active: !account.is_active })}>{account.is_active ? "停用" : "启用"}</Button></td></tr>)}{!loading && accounts.length === 0 && <tr><td className="p-6 text-center text-muted-foreground" colSpan={4}>暂无账户</td></tr>}</tbody></table></div></section></main>;
}
