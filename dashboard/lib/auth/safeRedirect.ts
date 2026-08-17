const DEFAULT_REDIRECT = "/dashboard";

/** The login page's `?next=` query param is attacker-controllable (a
 * phishing link can set it to anything) and gets handed to
 * router.push() client-side after a successful login -- without this
 * check, `next=https://evil.example` or the protocol-relative
 * `next=//evil.example` would be an open redirect straight out of a
 * real login flow. Only a same-origin, single-leading-slash path is
 * ever allowed through; anything else falls back to /dashboard. */
export function sanitizeNextPath(next: string | undefined | null): string {
  if (!next) return DEFAULT_REDIRECT;
  if (!next.startsWith("/")) return DEFAULT_REDIRECT;
  if (next.startsWith("//")) return DEFAULT_REDIRECT; // protocol-relative
  if (next.startsWith("/\\")) return DEFAULT_REDIRECT; // backslash trick some browsers treat as //
  return next;
}
