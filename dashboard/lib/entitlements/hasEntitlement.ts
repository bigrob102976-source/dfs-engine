import { computeUserAccess } from "./computeAccess";

export function userHasEntitlement(user: { id: string; role: string }, key: string): boolean {
  const access = computeUserAccess(user);
  return access.isAdmin || access.entitlementKeys.has(key);
}
