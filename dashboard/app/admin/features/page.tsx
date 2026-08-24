import { FeatureFlagSelect } from "@/components/admin/FeatureFlagSelect";
import { DataCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { listFeatureFlags } from "@/lib/db/featureFlags";
import { listSports } from "@/lib/db/sports";

export const dynamic = "force-dynamic";

export default async function AdminFeaturesPage() {
  const [flags, sports] = await Promise.all([listFeatureFlags(), listSports()]);
  const sportName = (code: string) => sports.find((s) => s.code === code)?.name ?? code;

  return (
    <div>
      <PageHeader
        title="Feature Flags"
        description="DISABLED hides a feature from everyone, including admins -- a real kill switch. ADMIN_ONLY restricts visibility to admins regardless of entitlement/subscription."
      />
      <DataCard title="Feature Catalog">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border text-[10px] uppercase tracking-wide text-text-faint">
              <th className="py-2 font-medium">Feature</th>
              <th className="py-2 font-medium">Sport</th>
              <th className="py-2 font-medium">State</th>
            </tr>
          </thead>
          <tbody>
            {flags.map((flag) => (
              <tr key={flag.key} className="border-b border-border-subtle last:border-0">
                <td className="py-2 text-text">{flag.label}</td>
                <td className="py-2 text-text-muted">{sportName(flag.sport_code)}</td>
                <td className="py-2">
                  <FeatureFlagSelect flagKey={flag.key} state={flag.state} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataCard>
    </div>
  );
}
