import { fetchInstances } from "@/lib/api";
import InstanceCard from "@/components/instance-card";

export const revalidate = 0; // sempre pegar dados mais recentes

export default async function Page() {
  const instances = await fetchInstances();

  return (
    <main className="mx-auto max-w-6xl p-4">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">Finger Dashboard</h1>
        <p className="text-sm text-gray-600">
          Status das instâncias, VPN, streams, últimos registros e erros.
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
