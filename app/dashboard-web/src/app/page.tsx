import { fetchInstances } from "@/lib/api";
import InstanceCard from "@/components/instance-card";
import type { Instance } from "@/types";

export const revalidate = 0; // sempre pegar dados mais recentes

function createMissingServerPlaceholders(instances: Instance[]): Instance[] {
  if (instances.length === 0) return [];

  // Ordena instâncias por server_id
  const sortedInstances = [...instances].sort((a, b) => a.server_id - b.server_id);
  const result: Instance[] = [];

  const minServerId = sortedInstances[0].server_id;
  const maxServerId = sortedInstances[sortedInstances.length - 1].server_id;

  // Cria um mapa para busca rápida
  const instanceMap = new Map(sortedInstances.map((inst) => [inst.server_id, inst]));

  // Preenche a sequência completa
  for (let serverId = minServerId; serverId <= maxServerId; serverId++) {
    const existingInstance = instanceMap.get(serverId);

    if (existingInstance) {
      result.push(existingInstance);
    } else {
      // Placeholder OFFLINE para server_id faltante
      result.push({
        server_id: serverId,
        last_heartbeat: "",
        status: "OFFLINE",
        ip_address: null,
        info: {
          hostname: "N/A",
          platform: "N/A",
          cpu_percent: 0,
          memory_percent: 0,
          disk_percent: 0,
          processing_streams: 0,
          total_streams: 0,
          distribution_mode: "N/A",
          processing_stream_names: [],
          vpn: { in_use: false, interface: null, type: null },
          recent_errors: [],
        },
      });
    }
  }

  return result;
}

export default async function Page() {
  const rawInstances = await fetchInstances();
  const instances = createMissingServerPlaceholders(rawInstances);

  return (
    <main className="mx-auto max-w-6xl p-4">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">Finger Dashboard</h1>
        <p className="text-sm text-gray-600">
          Status das instâncias, VPN, streams e erros.
        </p>
      </header>

      {instances.length === 0 ? (
        <div className="text-gray-500">Nenhuma instância encontrada.</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {instances.map((inst) => (
            <InstanceCard key={inst.server_id} instance={inst} />
          ))}
        </div>
      )}
    </main>
  );
}
