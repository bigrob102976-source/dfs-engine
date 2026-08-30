/** The origin for links a user clicks outside the app (email
 * verification, password reset). request.url's own origin reflects
 * Next.js's internal listening address (localhost:8080 in this
 * deployment), not the domain the browser actually used, because this
 * app sits behind Railway's edge proxy and Route Handlers don't
 * reconstruct request.url from the original Host header. Railway
 * auto-injects RAILWAY_PUBLIC_DOMAIN with the real public hostname for
 * exactly this reason -- prefer it whenever set, and fall back to
 * request.url's own origin only for local dev/test where no Railway
 * environment exists (preserving existing behavior there unchanged). */
export function getPublicOrigin(request: Request): string {
  const domain = process.env.RAILWAY_PUBLIC_DOMAIN;
  if (domain) return `https://${domain.replace(/^https?:\/\//, "")}`;
  return new URL(request.url).origin;
}
