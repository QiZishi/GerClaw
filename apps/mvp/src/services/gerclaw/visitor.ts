let inMemoryVisitorId: string | null = null;

export function getGerclawVisitorId(): string {
  if (inMemoryVisitorId) return inMemoryVisitorId;
  if (typeof window === "undefined") {
    throw new Error("访客身份只能在浏览器中初始化");
  }

  const created = crypto.randomUUID().replaceAll("-", "");
  inMemoryVisitorId = created;
  return created;
}
