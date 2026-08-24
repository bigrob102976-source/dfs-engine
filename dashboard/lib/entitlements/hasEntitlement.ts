import { computeUserAccess } from "./computeAccess";

export async function userHasEntitlement(user: { id: string; role: string }, key: string): Promise<boolean> {
  const access = await computeUserAccess(user);
  return access.isAdmin || access.entitlementKeys.has(key);
}
