"use client";

import { useEffect, useState } from "react";
import type { Instance, MusicRecord } from "@/types";
import { fetchLastRecords } from "@/lib/api";

interface InstanceCardProps {
  instance: Instance;
}

export default function InstanceCard({ instance }: InstanceCardProps) {
  const [records, setRecords] = useState<MusicRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await onRefresh?.();
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    handleRefresh();
    // Atualização periódica leve
    const id = setInterval(handleRefresh, 20000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instance.server_id]);

  const vpn = instance.info.vpn;
  const streams = instance.info.processing_stream_names || [];

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          Servidor #{instance.server_id} • {instance.status}
        </h3>
        <button
          onClick={handleRefresh}
          className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-700"
          aria-label="Atualizar registros"
        >
          Atualizar
        </button>
      </div>

      <div className="mt-2 grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
        <div>
          <div>Host: {instance.info.hostname || "-"}</div>
          <div>IP: {instance.ip_address || "-"}</div>
          <div>SO: {instance.info.platform || "-"}</div>
          <div>
            Distribuição: {instance.info.distribution_mode || "-"} • Streams:{" "}
            {instance.info.processing_streams ?? 0}/{instance.info.total_streams ?? 0}
          </div>
        </div>
        <div>
          <div>CPU: {instance.info.cpu_percent ?? 0}%</div>
          <div>Memória: {instance.info.memory_percent ?? 0}%</div>
          <div>Disco: {instance.info.disk_percent ?? 0}%</div>
          <div>
            VPN:{" "}
            {vpn?.in_use
              ? `${vpn.type || "desconhecida"} (${vpn.interface || "s/iface"})`
              : "não"}
          </div>
        </div>
      </div>

      <div className="mt-3">
        <div className="font-medium">Streams processados:</div>
        {streams.length ? (
          <ul className="mt-1 list-inside list-disc space-y-1">
            {streams.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-gray-500">Nenhum stream nesta instância.</div>
        )}
      </div>

      <div className="mt-4">
        <div className="font-medium">Últimos 5 registros (DB):</div>
        {loading ? (
          <div className="text-sm text-gray-500">Carregando…</div>
        ) : error ? (
          <div className="text-sm text-red-600">{error}</div>
        ) : records.length ? (
          <ul className="mt-1 space-y-1">
            {records.map((r, idx) => (
              <li key={`${r.date}-${r.time}-${idx}`} className="text-sm">
                <span className="font-semibold">{r.time}</span> • {r.name}:{" "}
                <span className="italic">{r.song_title}</span> — {r.artist}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-gray-500">Sem registros recentes.</div>
        )}
      </div>

      {instance.info.recent_errors && instance.info.recent_errors.length > 0 && (
        <div className="mt-4">
          <div className="font-medium text-red-700">Erros recentes:</div>
          <ul className="mt-1 space-y-1">
            {instance.info.recent_errors.slice(0, 5).map((e, i) => (
              <li key={i} className="text-sm text-red-600">
                [{e.timestamp}] {e.level}: {e.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}