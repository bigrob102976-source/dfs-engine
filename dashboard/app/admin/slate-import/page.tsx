import { SlateImportPanel } from "@/components/admin/SlateImportPanel";
import { DataCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { getTodayEasternDate } from "@/lib/currentDate";

export const dynamic = "force-dynamic";

/** BREAK-GLASS ADMIN CSV UPLOAD -- ADMIN-only (gated by
 * app/admin/layout.tsx's requireAdmin(), same as every other /admin/*
 * page). DraftKings Unofficial remains the normal automatic production
 * source (see worker/run_dk_fetch_worker.ps1) -- this page exists so the
 * owner can recover a real MLB slate in minutes from a manually
 * downloaded DraftKings CSV if that automatic collector is ever
 * unavailable, without opening a terminal, Railway, or VS Code. */
export default function AdminSlateImportPage() {
  const today = getTodayEasternDate();

  return (
    <div>
      <PageHeader
        title="MLB Slate Import (CSV)"
        description="Break-glass recovery: import a real DraftKings salary-export CSV directly, if the automatic collector is unavailable. Admin-only -- never a customer-facing or automatic-fallback source."
      />

      <DataCard title="Upload DraftKings MLB CSV">
        <SlateImportPanel defaultDate={today} />
      </DataCard>
    </div>
  );
}
