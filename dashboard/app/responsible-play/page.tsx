import Link from "next/link";

import { Footer } from "@/components/Footer";

export const metadata = {
  title: "Responsible Play — Big Money DFS",
  description: "Daily fantasy sports involves financial risk. Play within your means.",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-base font-semibold text-text">{title}</h2>
      <div className="mt-2 space-y-3 text-sm leading-relaxed text-text-muted">{children}</div>
    </section>
  );
}

export default function ResponsiblePlayPage() {
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-12">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-faint">
          <Link href="/" className="hover:underline">
            Big Money DFS
          </Link>
        </p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-text">Responsible Play</h1>

        <div className="mt-4 rounded-[var(--radius-control)] border border-gold/40 bg-bg-panel p-4 text-sm leading-relaxed text-text">
          Daily fantasy sports involve real financial risk. <strong>Never enter a contest with, or wager, money you
          cannot afford to lose.</strong> Big Money DFS is a research and analytics tool — it does not run contests,
          does not hold your money, and nothing in this product changes the fact that any contest you enter is
          real-money risk.
        </div>

        <Section title="Projections do not guarantee results">
          <p>
            Every projection, ranking, ownership estimate, and &quot;value&quot; or &quot;leverage&quot; score in
            this product is a statistical estimate, not a promise. Real games have outcomes no model can fully
            predict — injuries, game-flow, weather, officiating, and simple variance all affect real results. Treat
            every number in this product as one input to your own judgment, never as a certainty.
          </p>
        </Section>

        <Section title="Signs DFS may be a problem, not entertainment">
          <p>
            Consider stepping back, and consider reaching out to one of the resources below, if you notice:
            spending more money or time on contests than you planned; chasing losses by increasing stakes; entering
            contests to escape stress or other problems rather than for enjoyment; hiding your play or spending from
            people close to you; or feeling unable to stop or cut back even when you want to.
          </p>
        </Section>

        <Section title="Get help">
          <div className="rounded-[var(--radius-control)] border border-border bg-bg-panel p-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-text-faint">
              Placeholder — needs jurisdiction-specific legal/compliance review
            </p>
            <p className="mt-2">
              The resources below are widely recognized starting points in the United States, but the exact
              resource(s) that should be listed here depend on the jurisdiction(s) where Big Money DFS is actually
              offered, and in some jurisdictions a specific hotline or self-exclusion program is a legal
              requirement, not just a courtesy link. Do not treat this list as complete or launch-ready without
              that review.
            </p>
            <ul className="mt-3 list-inside list-disc space-y-1">
              <li>
                National Problem Gambling Helpline (US) —{" "}
                <a href="tel:1-800-522-4700" className="text-accent hover:underline">
                  1-800-522-4700
                </a>{" "}
                — 24/7, confidential
              </li>
              <li>
                National Council on Problem Gambling —{" "}
                <a href="https://www.ncpgambling.org" target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  ncpgambling.org
                </a>
              </li>
              <li>
                Text support (US) — text &quot;GAMB&quot; to{" "}
                <a href="sms:53342" className="text-accent hover:underline">
                  53342
                </a>
              </li>
            </ul>
          </div>
        </Section>

        <Section title="Age and eligibility">
          <p>
            Big Money DFS is not intended for anyone under the age of majority in their jurisdiction, and is not
            intended for use where daily fantasy sports or a research/analytics product like this one is restricted
            by local law. See the <Link href="/terms" className="text-accent hover:underline">Terms of Service</Link> for more.
          </p>
        </Section>
      </main>
      <Footer />
    </div>
  );
}
