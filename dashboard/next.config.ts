import type { NextConfig } from "next";

// Launch Blocker Sprint 1 (2026-09-13): production security headers.
// Verified against what the app actually does before writing this, so
// nothing here is a guess:
//   - Payments (lib/billing/stripeClient.ts) use the server-side Stripe
//     Node SDK only -- no @stripe/stripe-js, no js.stripe.com script, no
//     embedded Stripe Elements iframe anywhere in the codebase.
//     Checkout/portal is a full-page `window.location.href = url`
//     redirect to Stripe's hosted pages (CheckoutButton.tsx,
//     ManageSubscriptionButton.tsx) -- a top-level navigation, which
//     CSP's standard directives (script-src/frame-src/connect-src/
//     form-action) do not restrict at all. No Stripe-specific CSP
//     exception is needed for this to keep working.
//   - `<script dangerouslySetInnerHTML>` in app/layout.tsx (the
//     pre-paint theme-init script) is a real inline script, and
//     Next.js's own framework runtime also relies on inline
//     scripts/styles it injects itself. Without a nonce-based CSP
//     (a larger change than this sprint's scope -- would need
//     middleware to mint a per-request nonce and thread it through
//     both the response header and that inline <script> tag), the
//     honest, non-breaking choice is 'unsafe-inline' for script-src and
//     style-src. This is a real, documented gap versus a nonce-based
//     CSP -- worth tightening in a follow-up, not pretended away here.
//   - No third-party analytics/tracking script exists in the codebase
//     (grepped for Google Analytics/gtag/Mixpanel/Segment/PostHog/
//     Amplitude/Plausible/Hotjar -- none found), so connect-src/
//     script-src stay scoped to 'self' with no allowlisted third-party
//     origins.
//   - img-src allows https: broadly because player/team imagery and any
//     future CDN-hosted asset should not require a CSP change to render;
//     data: is required for small inline SVG/data-URI images already
//     used in the UI.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-src 'none'",
  "frame-ancestors 'none'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const SECURITY_HEADERS = [
  // Only meaningful over HTTPS (which Railway serves in production);
  // harmless in local HTTP dev -- browsers ignore it there.
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Backward-compatible with browsers that don't honor CSP
  // frame-ancestors yet; both say the same thing (never framed).
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Content-Security-Policy", value: CSP },
];

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

export default nextConfig;
