"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { DangerButton, PrimaryButton, SecondaryButton } from "@/components/ui/Button";

interface Plan {
  id: string;
  name: string;
}

interface EntitlementOption {
  key: string;
  label: string;
}

async function patchUser(userId: string, body: Record<string, unknown>): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`/api/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) return { ok: false, error: data.error ?? "Something went wrong." };
  return { ok: true };
}

/** A single sensitive action, always behind an explicit confirm step --
 * clicking the primary button never immediately mutates anything. */
function ConfirmAction({
  label,
  confirmText,
  onConfirm,
  danger = false,
  children,
}: {
  label: string;
  confirmText: string;
  onConfirm: () => Promise<{ ok: boolean; error?: string }>;
  danger?: boolean;
  children?: React.ReactNode;
}) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setSubmitting(true);
    setError(null);
    const result = await onConfirm();
    if (!result.ok) {
      setError(result.error ?? "Something went wrong.");
      setSubmitting(false);
      return;
    }
    setConfirming(false);
    setSubmitting(false);
    router.refresh();
  }

  if (confirming) {
    return (
      <div className={`rounded border p-3 ${danger ? "border-red/40 bg-red/10" : "border-border bg-bg-panel-raised"}`}>
        {children}
        <p className="mb-2 mt-2 text-xs text-text">{confirmText}</p>
        <div className="flex gap-2">
          <SecondaryButton onClick={() => setConfirming(false)} disabled={submitting} className="text-xs">
            Cancel
          </SecondaryButton>
          {danger ? (
            <DangerButton onClick={handleConfirm} disabled={submitting} className="text-xs">
              {submitting ? "Working..." : "Confirm"}
            </DangerButton>
          ) : (
            <PrimaryButton onClick={handleConfirm} disabled={submitting} className="text-xs">
              {submitting ? "Working..." : "Confirm"}
            </PrimaryButton>
          )}
        </div>
        {error && <p className="mt-2 text-xs text-red">{error}</p>}
      </div>
    );
  }

  return (
    <SecondaryButton onClick={() => setConfirming(true)} className="w-full text-xs">
      {label}
    </SecondaryButton>
  );
}

export function UserAdminActions({
  userId,
  role,
  disabled,
  hasComplimentary,
  hasSubscription,
  plans,
  entitlementsCatalog,
}: {
  userId: string;
  role: string;
  disabled: boolean;
  hasComplimentary: boolean;
  hasSubscription: boolean;
  plans: Plan[];
  entitlementsCatalog: EntitlementOption[];
}) {
  const router = useRouter();
  const [trialDays, setTrialDays] = useState(7);
  const [compPlanId, setCompPlanId] = useState(plans[0]?.id ?? "");
  const [entitlementKey, setEntitlementKey] = useState(entitlementsCatalog[0]?.key ?? "");

  return (
    <div className="flex flex-col gap-3">
      <ConfirmAction
        label={role === "ADMIN" ? "Demote to Member" : "Promote to Admin"}
        confirmText={role === "ADMIN" ? "Remove admin access for this user?" : "Grant this user full admin access?"}
        danger={role === "ADMIN"}
        onConfirm={() => patchUser(userId, { action: "change_role", role: role === "ADMIN" ? "MEMBER" : "ADMIN" })}
      />

      <ConfirmAction
        label={disabled ? "Restore Account" : "Disable Account"}
        confirmText={disabled ? "Restore this account's access?" : "Disable this account? They will be signed out immediately and unable to log in."}
        danger={!disabled}
        onConfirm={() => patchUser(userId, { action: disabled ? "restore_account" : "disable_account" })}
      />

      {hasSubscription && (
        <ConfirmAction label="Extend Trial" confirmText={`Extend this user's trial by ${trialDays} day(s)?`} onConfirm={() => patchUser(userId, { action: "extend_trial", days: trialDays })}>
          <label className="flex items-center gap-2 text-xs text-text-muted">
            Days
            <input
              type="number"
              min={1}
              max={90}
              value={trialDays}
              onChange={(e) => setTrialDays(Number(e.target.value))}
              className="w-16 rounded border border-border bg-bg-panel px-2 py-1 text-text"
            />
          </label>
        </ConfirmAction>
      )}

      {hasComplimentary ? (
        <ConfirmAction
          label="Remove Complimentary Access"
          confirmText="Remove this user's complimentary access?"
          danger
          onConfirm={() => patchUser(userId, { action: "remove_complimentary" })}
        />
      ) : (
        <ConfirmAction label="Grant Complimentary Access" confirmText="Grant free complimentary access on this plan?" onConfirm={() => patchUser(userId, { action: "grant_complimentary", planId: compPlanId })}>
          <label className="flex items-center gap-2 text-xs text-text-muted">
            Plan
            <select value={compPlanId} onChange={(e) => setCompPlanId(e.target.value)} className="rounded border border-border bg-bg-panel px-2 py-1 text-text">
              {plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </ConfirmAction>
      )}

      {entitlementsCatalog.length > 0 && (
        <ConfirmAction
          label="Grant Individual Entitlement"
          confirmText="Grant this specific entitlement, independent of their plan/subscription?"
          onConfirm={async () => {
            const res = await fetch(`/api/admin/users/${userId}/entitlements`, {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ entitlementKey }),
            });
            const data = await res.json();
            if (!res.ok) return { ok: false, error: data.error };
            router.refresh();
            return { ok: true };
          }}
        >
          <label className="flex items-center gap-2 text-xs text-text-muted">
            Entitlement
            <select value={entitlementKey} onChange={(e) => setEntitlementKey(e.target.value)} className="rounded border border-border bg-bg-panel px-2 py-1 text-text">
              {entitlementsCatalog.map((e) => (
                <option key={e.key} value={e.key}>
                  {e.label}
                </option>
              ))}
            </select>
          </label>
        </ConfirmAction>
      )}
    </div>
  );
}

export function RevokeEntitlementButton({ userId, entitlementKey, label }: { userId: string; entitlementKey: string; label: string }) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);

  async function handleClick() {
    setSubmitting(true);
    await fetch(`/api/admin/users/${userId}/entitlements?entitlementKey=${encodeURIComponent(entitlementKey)}`, { method: "DELETE" });
    setSubmitting(false);
    router.refresh();
  }

  return (
    <button type="button" onClick={handleClick} disabled={submitting} className="text-[11px] text-red hover:underline disabled:opacity-50">
      Revoke {label}
    </button>
  );
}
