import Link from "next/link";

import { Footer } from "@/components/Footer";

export const metadata = {
  title: "Support — Big Money DFS",
  description: "Get help with your Big Money DFS account.",
};

// Sprint 1 (2026-09-13): no real support email/address was found
// anywhere in this codebase (checked env files, config, and every
// existing page/doc). Per instruction, this is a clearly marked
// configuration placeholder, not an invented address -- replace with
// the real destination before launch, e.g. via a
// NEXT_PUBLIC_SUPPORT_EMAIL environment variable read here instead of
// this constant.
const SUPPORT_EMAIL: string | null = null;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-base font-semibold text-text">{title}</h2>
      <div className="mt-2 space-y-3 text-sm leading-relaxed text-text-muted">{children}</div>
    </section>
  );
}

export default function SupportPage() {
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-12">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-faint">
          <Link href="/" className="hover:underline">
            Big Money DFS
          </Link>
        </p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-text">Support</h1>

        <Section title="Contact us">
          {SUPPORT_EMAIL ? (
            <p>
              For account, billing, or product questions, email{" "}
              <a href={`mailto:${SUPPORT_EMAIL}`} className="text-accent hover:underline">
                {SUPPORT_EMAIL}
              </a>
              .
            </p>
          ) : (
            <div className="rounded-[var(--radius-control)] border border-gold/40 bg-bg-panel p-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-gold">Support address not yet configured</p>
              <p className="mt-2">
                No support email or contact channel has been set up in the product yet. This page is real and
                reachable, but there is nowhere for a message to go until a real address (or a support tool
                integration) is configured — this must be set before public launch, not left as a placeholder.
              </p>
            </div>
          )}
        </Section>

        <Section title="Billing questions">
          <p>
            Subscription changes and cancellation are available from your account settings once you&apos;re logged
            in. If you need help with a charge, include your account email and, if possible, the approximate date of
            the charge when you reach out.
          </p>
        </Section>

        <Section title="Data requests">
          <p>
            To request a copy of your data, or to request deletion of your account, see the{" "}
            <Link href="/privacy" className="text-accent hover:underline">
              Privacy Policy
            </Link>{" "}
            and use the contact method above — there is no self-service option for this yet.
          </p>
        </Section>

        <Section title="Something not working?">
          <p>
            If you notice stale or missing data (a slate, a projection, an ownership number, or a Vegas line that
            looks wrong or out of date), the product is designed to show an honest status for that instead of a
            guess — for example &quot;stale,&quot; &quot;awaiting projection,&quot; or &quot;awaiting Vegas.&quot; If
            you see something that looks like a bug rather than an honest status message, let us know using the
            contact method above.
          </p>
        </Section>
      </main>
      <Footer />
    </div>
  );
}
