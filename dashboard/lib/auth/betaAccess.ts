import { isPrivateBetaEnabled } from "../env";
import { isAdminRole } from "./roles";
import type { CurrentUser } from "./session";

// Milestone 30: PRIVATE_BETA=true restricts the MEMBER product to ADMIN +
// explicitly beta-approved users -- a temporary entitlement/access gate
// in FRONT of the product (like disabled_at), not a replacement for the
// subscription/entitlement architecture. When PRIVATE_BETA is not set
// (the default), every authenticated user has access, exactly as before
// this milestone -- this function is a no-op gate until an operator
// explicitly turns private beta on.

export function hasProductAccess(user: CurrentUser): boolean {
  if (!isPrivateBetaEnabled()) return true;
  if (isAdminRole(user.role)) return true;
  return user.betaAccessGrantedAt != null;
}
