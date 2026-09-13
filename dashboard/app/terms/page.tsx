import Link from "next/link";

import { Footer } from "@/components/Footer";

export const metadata = {
  title: "Terms of Service — Big Money DFS",
  description: "The terms governing use of Big Money DFS's fantasy sports research and analytics product.",
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

export default function TermsPage() {
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-12">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-faint">
          <Link href="/" className="hover:underline">
            Big Money DFS
          </Link>
        </p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-text">Terms of Service</h1>
        <p className="mt-1 text-xs text-text-faint">Last updated: {LAST_UPDATED}</p>

        <div className="mt-4 rounded-[var(--radius-control)] border border-gold/40 bg-bg-panel p-3 text-xs leading-relaxed text-text-muted">
          <strong className="text-text">This page is not legal advice.</strong> It is a good-faith description of
          how Big Money DFS operates, written by the product team. Before public launch it should be reviewed by a
          qualified attorney familiar with daily fantasy sports and analytics-product regulation in the
          jurisdiction(s) where the service will be offered, and updated to reflect that review.
        </div>

        <Section title="1. What Big Money DFS is">
          <p>
            Big Money DFS is a fantasy sports research and analytics product. It provides projections, player
            rankings, ownership estimates, matchup and odds information, and lineup-construction tools intended to
            help users research and analyze daily fantasy sports (DFS) contests offered by third-party operators
            (such as DraftKings). Big Money DFS does not operate a fantasy sports contest, does not accept wagers,
            and does not pay out winnings — any contest you enter and any money you risk is between you and the
            third-party DFS operator you choose to use, under that operator&apos;s own rules.
          </p>
        </Section>

        <Section title="2. No guarantee of winnings">
          <p>
            Projections, rankings, ownership estimates, &quot;value,&quot; &quot;leverage,&quot; and similar scores
            shown in the product are statistical estimates generated from historical and current data. They are
            informational only and are not a guarantee, promise, or prediction of any specific outcome. Past
            performance of a projection, model, or ranking is not indicative of future results. You should not rely
            on any single number in this product as a certainty, and you are solely responsible for how you use this
            information in any contest you choose to enter.
          </p>
        </Section>

        <Section title="3. Your responsibility to comply with the law">
          <p>
            Daily fantasy sports are regulated differently across countries, states, provinces, and other
            jurisdictions — in some places DFS contests are unrestricted, in others they are regulated or licensed,
            and in others they are restricted or unavailable. You are solely responsible for determining whether
            participating in DFS contests, and using a research/analytics product like Big Money DFS in connection
            with them, is lawful for you given your age, location, and applicable local law. Big Money DFS is not
            available to anyone under the age of majority in their jurisdiction (18, or the higher age required
            where you live) and is not intended for use in any jurisdiction where its use would be unlawful.
          </p>
        </Section>

        <Section title="4. Service availability and data accuracy">
          <p>
            Big Money DFS depends on third-party data sources — including, without limitation, contest/slate and
            salary data published by DFS operators, sports statistics providers, and sportsbook odds providers — and
            on automated processes that fetch, compute, and refresh that data on a schedule. This data can be
            delayed, temporarily unavailable, incomplete, or occasionally incorrect, whether due to an upstream
            provider issue, a scheduled or unscheduled maintenance window, or a defect in our own systems. Where
            current data is not available, the product is designed to show that state honestly (for example, as
            &quot;stale,&quot; &quot;awaiting projection,&quot; or a similar explicit status) rather than substitute
            invented values — but we do not guarantee the product will always be available, current, or free of
            error, and we are not liable for a decision you make based on unavailable, delayed, or incorrect data.
          </p>
        </Section>

        <Section title="5. Accounts and acceptable use">
          <p>
            You must provide accurate information when creating an account and are responsible for maintaining the
            confidentiality of your login credentials and for all activity under your account. You agree not to: (a)
            access or attempt to access another user&apos;s account or data; (b) use automated means (scraping, bots,
            or unauthorized API access) to extract data from the product beyond normal interactive use; (c)
            circumvent or attempt to circumvent any rate limit, authentication requirement, or other access control;
            or (d) use the product for any unlawful purpose. We may suspend or terminate access for a violation of
            these terms.
          </p>
        </Section>

        <Section title="6. Subscriptions and billing">
          <p>
            Where Big Money DFS offers a paid subscription, the price, billing interval, and any trial period are
            disclosed at the time of purchase (see the Pricing page). Subscriptions renew automatically at the
            then-current price until canceled; you may cancel at any time through your account settings, and
            cancellation takes effect at the end of the current billing period unless stated otherwise at checkout.
            Payment processing is handled by a third-party payment processor (Stripe) — see the Privacy Policy for
            what that involves.
          </p>
        </Section>

        <Section title="7. Disclaimer of warranties">
          <p>
            THE PRODUCT AND ALL PROJECTIONS, RANKINGS, DATA, AND CONTENT WITHIN IT ARE PROVIDED &quot;AS IS&quot; AND
            &quot;AS AVAILABLE,&quot; WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING WITHOUT
            LIMITATION ANY WARRANTY OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, ACCURACY, OR
            NON-INFRINGEMENT, TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW.
          </p>
        </Section>

        <Section title="8. Limitation of liability">
          <p>
            TO THE MAXIMUM EXTENT PERMITTED BY LAW, BIG MONEY DFS AND ITS OPERATORS WILL NOT BE LIABLE FOR ANY
            INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF WINNINGS, PROFITS, OR
            DATA, ARISING OUT OF OR RELATED TO YOUR USE OF THE PRODUCT OR ANY DECISION MADE USING ITS PROJECTIONS,
            RANKINGS, OR OTHER CONTENT — INCLUDING A DECISION TO ENTER, OR NOT ENTER, ANY THIRD-PARTY DFS CONTEST.
            This is a general placeholder limitation appropriate for an informational analytics product; the exact
            scope and any required jurisdiction-specific carve-outs need attorney review before launch.
          </p>
        </Section>

        <Section title="9. Changes to these terms">
          <p>
            We may update these terms from time to time. If we make a material change, we will update the &quot;Last
            updated&quot; date above. Continued use of the product after a change takes effect constitutes
            acceptance of the updated terms.
          </p>
        </Section>

        <Section title="10. Contact">
          <p>
            Questions about these terms can be sent through the <Link href="/support" className="text-accent hover:underline">Support</Link> page.
          </p>
        </Section>
      </main>
      <Footer />
    </div>
  );
}
