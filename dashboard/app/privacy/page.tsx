import Link from "next/link";

import { Footer } from "@/components/Footer";

export const metadata = {
  title: "Privacy Policy — Big Money DFS",
  description: "What information Big Money DFS collects, why, and how it is stored.",
};

const LAST_UPDATED = "2026-09-13";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-base font-semibold text-text">{title}</h2>
      <div className="mt-2 space-y-3 text-sm leading-relaxed text-text-muted">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-12">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-faint">
          <Link href="/" className="hover:underline">
            Big Money DFS
          </Link>
        </p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-text">Privacy Policy</h1>
        <p className="mt-1 text-xs text-text-faint">Last updated: {LAST_UPDATED}</p>

        <div className="mt-4 rounded-[var(--radius-control)] border border-gold/40 bg-bg-panel p-3 text-xs leading-relaxed text-text-muted">
          <strong className="text-text">This page is not legal advice.</strong> It describes what the product
          actually does today, to the best of our knowledge, so it can serve as a starting point for legal review —
          it should be reviewed by a qualified attorney (and adjusted for any jurisdiction-specific disclosure
          requirement, such as GDPR/CCPA-style rights) before public launch.
        </div>

        <Section title="1. Account information">
          <p>
            When you create an account, we store your email address, a securely hashed password (or equivalent
            credential), your account role, and account status fields such as whether your email has been verified.
            We use this to authenticate you and operate your account — we do not sell this information.
          </p>
        </Section>

        <Section title="2. Authentication / sessions">
          <p>
            When you log in, we create a session record (a random session token, your account ID, the device/browser
            user agent string, and an expiration time) and store its token in a cookie on your device. That cookie is
            marked <code className="text-text">httpOnly</code> (not readable by page scripts),{" "}
            <code className="text-text">sameSite=lax</code>, and (in production) <code className="text-text">secure</code> (HTTPS
            only). Logging out deletes the corresponding session record on our servers; a session also expires
            automatically after a fixed period of inactivity.
          </p>
        </Section>

        <Section title="3. Payments">
          <p>
            If you subscribe to a paid plan, payment processing (collecting and storing your card details, running
            the charge) is handled entirely by our payment processor, Stripe — we do not receive or store your full
            card number. We store a reference to your Stripe customer/subscription IDs and subscription status
            (plan, billing interval, trial/renewal dates) so your account reflects the correct access level, and we
            record the Stripe webhook events that keep that status in sync.
          </p>
        </Section>

        <Section title="4. Product usage logging">
          <p>
            We record a limited internal log of certain in-product actions (an event type, an optional small
            metadata payload, and a timestamp, associated with your account where you are logged in) for our own
            operational purposes — for example, understanding which features are used and diagnosing problems. We do
            not use any third-party analytics, advertising, or tracking service (no Google Analytics, ad pixels, or
            similar) — this logging stays inside our own systems.
          </p>
        </Section>

        <Section title="5. Cookies and local storage">
          <p>
            Beyond the session cookie described above, the product stores a small number of preferences directly in
            your browser&apos;s local storage — for example, whether the sidebar is collapsed, or in-progress
            optimizer settings (locks, exclusions, exposure limits) for the sport you&apos;re viewing. These values
            stay on your device, are never transmitted to our servers, and are not a tracking mechanism — clearing
            your browser&apos;s site data removes them.
          </p>
        </Section>

        <Section title="6. Third-party infrastructure">
          <p>
            The product runs on Railway (application hosting and its managed Postgres database), uses an
            S3-compatible object storage provider for cached research/projection artifacts, and uses Stripe for
            payments (see above). Underlying DFS slate/salary data is sourced from DraftKings&apos; own publicly
            reachable endpoints, and game/odds context comes from third-party sports-data and sportsbook-odds
            providers. None of these providers receive your account credentials; where they receive any information
            about you at all, it is limited to what&apos;s described above (e.g., Stripe receiving your billing
            details directly to process a charge).
          </p>
        </Section>

        <Section title="7. Data retention and deletion">
          <p>
            We retain account and subscription records for as long as your account is active, and for a reasonable
            period afterward for legitimate business, accounting, and legal purposes (for example, billing history).
            <strong className="text-text"> There is currently no self-service &quot;delete my account&quot; control in the
            product</strong> — to request deletion or export of your personal data, contact us through the{" "}
            <Link href="/support" className="text-accent hover:underline">
              Support
            </Link>{" "}
            page and we will handle the request manually. This section, including any required minimum retention
            periods and a self-service deletion flow, needs attorney and product review before this claim can be
            made more specific.
          </p>
        </Section>

        <Section title="8. Changes to this policy">
          <p>
            We may update this policy from time to time. If we make a material change, we will update the &quot;Last
            updated&quot; date above.
          </p>
        </Section>

        <Section title="9. Contact">
          <p>
            Questions about this policy, or a request to access/delete your data, can be sent through the{" "}
            <Link href="/support" className="text-accent hover:underline">
              Support
            </Link>{" "}
            page.
          </p>
        </Section>
      </main>
      <Footer />
    </div>
  );
}
