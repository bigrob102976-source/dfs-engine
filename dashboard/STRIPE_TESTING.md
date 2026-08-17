# Testing Stripe Billing Locally (Milestone 22)

Big Money DFS's Stripe integration is **test-mode only**. This doc has no secrets in it — every value below is a placeholder you fill in from your own Stripe test-mode dashboard.

## 1. Required environment variables

Add these to `dashboard/.env.local` (already gitignored — never commit it):

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_WEEKLY_PRICE_ID=price_...
STRIPE_MONTHLY_PRICE_ID=price_...
```

- `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` — from the Stripe Dashboard, **Test mode** toggle on, Developers → API keys. Only `sk_test_...` keys are accepted; the app refuses to initialize with an `sk_live_...` key (see `lib/billing/stripeConfig.ts`).
- `STRIPE_WEBHOOK_SECRET` — generated when you set up webhook forwarding (step 3 below).
- `STRIPE_WEEKLY_PRICE_ID` / `STRIPE_MONTHLY_PRICE_ID` — see step 2.

Without these, the app falls back to `DevBillingProvider` (local simulation, clearly labeled "Development Mode" in the UI) outside production, or a fail-closed "billing not configured" state in production. It never silently fakes real billing.

## 2. Create the two test-mode Products/Prices

In the Stripe Dashboard (test mode on):

1. Products → Add product → **Big Money DFS Weekly** → recurring price **$10.99 / week** → copy the Price ID into `STRIPE_WEEKLY_PRICE_ID`.
2. Products → Add product → **Big Money DFS Monthly** → recurring price **$29.99 / month** → copy the Price ID into `STRIPE_MONTHLY_PRICE_ID`.

The app never creates these automatically and never fabricates a price if the env var is missing — `/pricing`, `/subscribe`, and `/admin/system` all show a clear "not configured" state instead.

The 3-day trial is applied by the app at Checkout-session creation time (`subscription_data.trial_period_days`), not configured on the Price itself.

## 3. Forward webhooks to your local server

Install the [Stripe CLI](https://docs.stripe.com/stripe-cli), then:

```
stripe login
stripe listen --forward-to localhost:3000/api/billing/stripe/webhook
```

The CLI prints a `whsec_...` value — put that in `STRIPE_WEBHOOK_SECRET`. Keep `stripe listen` running while you test locally; each `npm run dev` restart doesn't need a new secret as long as `stripe listen` stays up.

## 4. Trigger test events

With `stripe listen` running:

```
stripe trigger checkout.session.completed
stripe trigger customer.subscription.created
stripe trigger customer.subscription.updated
stripe trigger customer.subscription.deleted
stripe trigger invoice.paid
stripe trigger invoice.payment_failed
```

Check `/admin/system`'s "Stripe Webhooks" card afterward — it shows processed/failed counts and the last successful event without exposing any payload contents or secrets.

## 5. End-to-end manual test

1. `npm run dev`, `stripe listen --forward-to localhost:3000/api/billing/stripe/webhook` running in another terminal.
2. Sign up a test account, go to `/pricing`, pick Weekly, land on `/subscribe`.
3. Click "Continue to Secure Checkout" — you're redirected to a real Stripe-hosted Checkout page (test mode banner visible in Stripe's own UI).
4. Use a [Stripe test card](https://docs.stripe.com/testing#cards) (e.g. `4242 4242 4242 4242`, any future expiry, any CVC).
5. On success you land on `/subscribe/success`, which polls until the webhook lands and shows "Trial Active."
6. Check `/account/billing` — full plan/status/trial/next-billing detail, plus "Manage Subscription" (opens the real Stripe Customer Portal).
7. In the Portal, cancel — `cancel_at_period_end` should flip to true; confirm on `/account/billing` and in `/admin/subscriptions`.

## Never required for this milestone

- A real `sk_live_...` key — the app refuses to use one.
- A real card — test cards only.
- Production credentials of any kind.
