"use client";

import { useEffect, useState } from "react";
import { ArrowLeftRight, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { switchAdministratorView } from "@/services/account";

type Account = {
  actor_id: string;
  username: string;
  role: "patient" | "doctor" | "admin";
  is_active: boolean;
  created_at: string;
};
type BadCaseStatus = "open" | "triaged" | "resolved" | "dismissed";
type BadCase = {
  id: string;
  source: string;
  reason_codes: string[];
  severity: string;
  status: BadCaseStatus;
  created_at: string;
};
type BadCaseSummary = {
  total: number;
  open_count: number;
  triaged_count: number;
  resolved_count: number;
  dismissed_count: number;
  execution_failure_count: number;
  negative_feedback_count: number;
  high_priority_count: number;
};

const csrf = () => document.cookie.split("; ").find((value) => value.startsWith("gerclaw_account_csrf="))?.split("=")[1] ?? "";

function SummaryMetric({ label, value, emphasized = false }: { label: string; value: number; emphasized?: boolean }) {
  return (
    <div className="rounded-lg border bg-card px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={emphasized ? "text-xl font-semibold text-destructive" : "text-xl font-semibold"}>{value}</p>
    </div>
  );
}

export function AdminDashboard() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [cases, setCases] = useState<BadCase[]>([]);
  const [summary, setSummary] = useState<BadCaseSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadSummary = async () => {
    const response = await fetch("/api/account/admin/bad-cases/summary", { cache: "no-store" });
    if (!response.ok) throw new Error("summary unavailable");
    setSummary(await response.json());
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [accountsResponse, casesResponse, summaryResponse] = await Promise.all([
        fetch("/api/account/admin/accounts", { cache: "no-store" }),
        fetch("/api/account/admin/bad-cases", { cache: "no-store" }),
        fetch("/api/account/admin/bad-cases/summary", { cache: "no-store" }),
      ]);
      if (!accountsResponse.ok || !casesResponse.ok || !summaryResponse.ok) throw new Error("load failed");
      setAccounts((await accountsResponse.json()).accounts);
      setCases((await casesResponse.json()).cases);
      setSummary(await summaryResponse.json());
    } catch {
      setError("暂时无法读取管理数据。");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, []);

  const updateAccount = async (actorId: string, patch: Partial<Pick<Account, "role" | "is_active">>) => {
    const response = await fetch(`/api/account/admin/accounts/${actorId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json", "x-gerclaw-csrf": csrf() },
      body: JSON.stringify(patch),
    });
    if (!response.ok) {
      setError("账户更新未完成。");
      return;
    }
    const next = await response.json();
    setAccounts((all) => all.map((account) => account.actor_id === actorId ? next : account));
  };

  const updateCase = async (id: string, status: BadCaseStatus) => {
    const response = await fetch(`/api/account/admin/bad-cases/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json", "x-gerclaw-csrf": csrf() },
      body: JSON.stringify({ status }),
    });
    if (!response.ok) {
      setError("处置状态未保存。");
      return;
    }
    const next = await response.json();
    setCases((all) => all.map((item) => item.id === id ? { ...item, ...next } : item));
    try {
      await loadSummary();
    } catch {
      setError("处置已保存，但汇总暂未刷新。");
    }
  };

  const switchView = async (role: "patient" | "doctor") => {
    await switchAdministratorView(role);
    window.location.assign("/");
  };

  return (
    <main className="min-h-screen bg-background p-4 sm:p-8">
      <section className="mx-auto max-w-5xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="grid size-11 place-items-center rounded-xl bg-primary text-primary-foreground"><ShieldCheck /></div>
            <div>
              <h1 className="text-2xl font-semibold">账户管理</h1>
              <p className="text-sm text-muted-foreground">账户与运行处置</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void switchView("patient")}><ArrowLeftRight />患者端</Button>
            <Button variant="outline" onClick={() => void switchView("doctor")}><ArrowLeftRight />医生端</Button>
            <Button variant="outline" onClick={() => void load()} disabled={loading}><RefreshCw />{loading ? "正在刷新" : "刷新"}</Button>
          </div>
        </header>

        {error && <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-destructive">{error}</p>}
        {loading && <InlineLoadingState message="正在读取管理数据" />}

        {summary && (
          <section aria-label="运行问题汇总" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <SummaryMetric label="待处理" value={summary.open_count} emphasized={summary.open_count > 0} />
            <SummaryMetric label="高优先级" value={summary.high_priority_count} emphasized={summary.high_priority_count > 0} />
            <SummaryMetric label="用户负反馈" value={summary.negative_feedback_count} />
            <SummaryMetric label="已处置" value={summary.resolved_count + summary.dismissed_count} />
          </section>
        )}

        <section className="overflow-hidden rounded-xl border">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/50 text-muted-foreground"><tr><th className="p-3">账号</th><th className="p-3">身份</th><th className="p-3">状态</th><th className="p-3">操作</th></tr></thead>
            <tbody>{accounts.map((account) => <tr key={account.actor_id} className="border-t"><td className="p-3 font-medium">{account.username}</td><td className="p-3"><select aria-label={`${account.username}身份`} value={account.role} disabled={account.role === "admin"} onChange={(event) => void updateAccount(account.actor_id, { role: event.target.value as "patient" | "doctor" })}><option value="patient">患者</option><option value="doctor">医生</option></select></td><td className="p-3">{account.is_active ? "正常" : "已停用"}</td><td className="p-3"><Button size="sm" variant="outline" disabled={account.role === "admin"} onClick={() => void updateAccount(account.actor_id, { is_active: !account.is_active })}>{account.is_active ? "停用" : "启用"}</Button></td></tr>)}</tbody>
          </table>
        </section>

        <section className="overflow-hidden rounded-xl border">
          <header className="border-b bg-muted/50 p-3"><h2 className="font-semibold">运行问题</h2></header>
          <table className="w-full text-left text-sm">
            <thead className="text-muted-foreground"><tr><th className="p-3">来源</th><th className="p-3">严重度</th><th className="p-3">状态</th><th className="p-3">处置</th></tr></thead>
            <tbody>
              {cases.map((item) => <tr key={item.id} className="border-t"><td className="p-3">{item.source}</td><td className="p-3">{item.severity}</td><td className="p-3">{item.status}</td><td className="p-3"><select aria-label="更新运行问题状态" value={item.status} onChange={(event) => void updateCase(item.id, event.target.value as BadCaseStatus)}><option value="open">待处理</option><option value="triaged">已分诊</option><option value="resolved">已解决</option><option value="dismissed">已关闭</option></select></td></tr>)}
              {!loading && cases.length === 0 && <tr><td className="p-5 text-center text-muted-foreground" colSpan={4}>暂无运行问题</td></tr>}
            </tbody>
          </table>
        </section>
      </section>
    </main>
  );
}
