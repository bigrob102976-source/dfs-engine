import { SportStatusToggle } from "@/components/admin/SportStatusToggle";
import { DataCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { listSports } from "@/lib/db/sports";

export const dynamic = "force-dynamic";

export default async function AdminSportsPage() {
  const sports = await listSports();

  return (
    <div>
      <PageHeader
        title="Sports"
        description="MLB is the only sport with real DFS logic today. Other sports are admin-only prep -- flipping them LIVE does not add functionality, it only changes visibility."
      />
      <DataCard title="Sports Catalog">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border text-[10px] uppercase tracking-wide text-text-faint">
              <th className="py-2 font-medium">Sport</th>
              <th className="py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {sports.map((sport) => (
              <tr key={sport.code} className="border-b border-border-subtle last:border-0">
                <td className="py-2 text-text">{sport.name}</td>
                <td className="py-2">
                  <SportStatusToggle code={sport.code} status={sport.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataCard>
    </div>
  );
}
