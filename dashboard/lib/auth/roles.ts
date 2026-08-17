// Roles are plain TEXT on users.role (no DB CHECK constraint) so a
// future role (e.g. SUPPORT, SUPER_ADMIN) can be introduced without a
// migration -- validated only here, in application code. VISITOR is
// never persisted: it's the implicit "no valid session" state.

export const ROLES = ["MEMBER", "ADMIN"] as const;
export type Role = (typeof ROLES)[number];

export function isValidRole(value: string): value is Role {
  return (ROLES as readonly string[]).includes(value);
}

export function isAdminRole(role: string): boolean {
  return role === "ADMIN";
}
