import { listActivePlans } from "@/lib/db/plans";
import {
  countActiveSubscribersByPlan,
  countCancellationsSince,
  countCurrentSubscribersByPlan,
  countSubscriptionsByStatus,
  countSubscriptionsCreatedSince,
  getTrialConversionStats,
} from "@/lib/db/subscriptions";

export interface AdminRevenueStats {
  mrrCents: number;
  arrCents: number;
  weeklyRevenueCents: number;
  monthlyRevenueCents: number;
  /** Currently-paying (status='active') subscribers, all plans combined. */
  activeSubscribers: number;
  /** Current subscribers (trialing/active/complimentary) per plan --
   * same "current" definition lib/admin/overviewStats.ts's Weekly/Monthly
   * Members cards use, kept consistent across both admin pages. */
  weeklySubscribers: number;
  monthlySubscribers: number;
  pastDueSubscribers: number;
  canceledSubscribers: number;
  newSubscribersThisMonth: number;
  activeTrials: number;
  trialConversionRatePct: number | null;
  cancellationsThisMonth: number;
  /** True churn requires point-in-time subscriber-count snapshots this
   * system doesn't retain yet -- always null (displayed as "--") rather
   * than approximated, per "never invent revenue/metrics." */
  churnRatePct: null;
}

function startOfCurrentMonthIso(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString();
}

/** No payment processor is connected -- every figure here is derived
 * from real local subscription rows and the seeded plan catalog, never
 * fabricated. Revenue-shaped concepts this system cannot rigorously
 * compute yet (refunds, true churn) are surfaced as null/`--`, not
 * guessed at. */
export function computeAdminRevenueStats(): AdminRevenueStats {
  const plans = listActivePlans();
  const weeklyPlan = plans.find((p) => p.billing_interval === "WEEKLY") ?? null;
  const monthlyPlan = plans.find((p) => p.billing_interval === "MONTHLY") ?? null;

  const weeklyRevenueCents = weeklyPlan ? Math.round(countActiveSubscribersByPlan(weeklyPlan.id) * weeklyPlan.price_cents * (52 / 12)) : 0;
  const monthlyRevenueCents = monthlyPlan ? countActiveSubscribersByPlan(monthlyPlan.id) * monthlyPlan.price_cents : 0;
  const mrrCents = weeklyRevenueCents + monthlyRevenueCents;

  const statusCounts = countSubscriptionsByStatus();
  const conversion = getTrialConversionStats();
  const since = startOfCurrentMonthIso();

  return {
    mrrCents,
    arrCents: mrrCents * 12,
    weeklyRevenueCents,
    monthlyRevenueCents,
    activeSubscribers: statusCounts.active,
    weeklySubscribers: weeklyPlan ? countCurrentSubscribersByPlan(weeklyPlan.id) : 0,
    monthlySubscribers: monthlyPlan ? countCurrentSubscribersByPlan(monthlyPlan.id) : 0,
    pastDueSubscribers: statusCounts.past_due,
    canceledSubscribers: statusCounts.canceled,
    newSubscribersThisMonth: countSubscriptionsCreatedSince(since),
    activeTrials: statusCounts.trialing,
    trialConversionRatePct: conversion.trialUsersEver > 0 ? (conversion.converted / conversion.trialUsersEver) * 100 : null,
    cancellationsThisMonth: countCancellationsSince(since),
    churnRatePct: null,
  };
}
