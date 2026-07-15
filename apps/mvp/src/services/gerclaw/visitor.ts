const VISITOR_STORAGE_KEY = "gerclaw:visitor-id";
const VISITOR_ID_PATTERN = /^[a-f0-9]{32}$/;

let inMemoryVisitorId: string | null = null;

export function getGerclawVisitorId(): string {
  if (inMemoryVisitorId) return inMemoryVisitorId;
  if (typeof window === "undefined") {
    throw new Error("访客身份只能在浏览器中初始化");
  }

  try {
    const stored = window.localStorage.getItem(VISITOR_STORAGE_KEY);
    if (stored && VISITOR_ID_PATTERN.test(stored)) {
      inMemoryVisitorId = stored;
      return stored;
    }
  } catch {
    // In-memory identity still converges concurrent requests in this browser tab.
  }

  const created = crypto.randomUUID().replaceAll("-", "");
  inMemoryVisitorId = created;
  try {
    window.localStorage.setItem(VISITOR_STORAGE_KEY, created);
  } catch {
    // Storage may be unavailable in strict privacy mode; the tab-local value remains stable.
  }
  return created;
}
