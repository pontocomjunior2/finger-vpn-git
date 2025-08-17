function getApiBase(): string {
  const isBrowser = typeof window !== "undefined";
  const envBase = isBrowser
    ? process.env.NEXT_PUBLIC_DASHBOARD_API_BASE
    : process.env.DASHBOARD_API_BASE;

  const base = (envBase?.trim() || "http://127.0.0.1:8080").replace(/\/+$/, "");
  return base;
}

export async function fetchInstances(): Promise<import("@/types").Instance[]> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/instances`, { cache: "no-store" });
  if (!res.ok) throw new Error("Falha ao carregar instâncias");
  return res.json();
}

export async function fetchLastRecords(
  serverId: number,
  limit = 5
): Promise<import("@/types").MusicRecord[]> {
  const base = getApiBase();
  const res = await fetch(
    `${base}/api/instances/${serverId}/last-records?limit=${limit}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error("Falha ao carregar últimos registros");
  return res.json();
}