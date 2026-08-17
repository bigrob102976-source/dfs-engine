import { listActivePlans } from "@/lib/db/plans";
import {
  countActiveSubscribersByPlan,
  countCurrentSubscribersByPlan,
  countSubscriptionsByStatus,
  getTrialConversionStats,
} from "@/lib/db/subscriptions";
import { countUsers } from "@/lib/db/users";

export interface AdminOverviewStats {
  totalUsers: number;
  activeMembers: number;
  activeTrials: number;
  weeklyMembers: number;
  monthlyMembers: number;
  canceledMembers: number;
  pastDue: number;
  complimentaryAccounts: number;
  mrrCents: number;
  arrCents: number;
  /** null means "cannot be calculated" (no one has ever trialed), not 0%. */
  trialConversionRatePct: number | null;
}

/** Real KPI figures derived entirely from local SQLite state -- no
 * payment processor is connected, so MRR/ARR are computed from the
 * seeded plan prices and actual current-subscriber counts, not
 * fabricated. $0 (zero active payers) is a valid computed answer;
 * trial conversion is null (displayed as "--") only when the
 * denominator is genuinely zero. */
export function computeAdminOverviewStats(): AdminOverviewStats {
  const statusCounts = countSubscriptionsByStatus();
  const plans = listActivePlans();
  const weeklyPlan = plans.find((p) => p.billing_interval === "WEEKLY") ?? null;
  const monthlyPlan = plans.find((p) => p.billing_interval === "MONTHLY") ?? null;

  let mrrCents = 0;
  if (weeklyPlan) {
    mrrCents += countActiveSubscribersByPlan(weeklyPlan.id) * weeklyPlan.price_cents * (52 / 12);
  }
  if (monthlyPlan) {
    mrrCents += countActiveSubscribersByPlan(monthlyPlan.id) * monthlyPlan.price_cents;
  }
  mrrCents = Math.round(mrrCents);

  const conversion = getTrialConversionStats();

  return {
    totalUsers: countUsers(),
    activeMembers: statusCounts.active,
    activeTrials: statusCounts.trialing,
    weeklyMembers: weeklyPlan ? countCurrentSubscribersByPlan(weeklyPlan.id) : 0,
    monthlyMembers: monthlyPlan ? countCurrentSubscribersByPlan(monthlyPlan.id) : 0,
    canceledMembers: statusCounts.canceled,
    pastDue: statusCounts.past_due,
    complimentaryAccounts: statusCounts.complimentary,
    mrrCents,
    arrCents: mrrCents * 12,
    trialConversionRatePct: conversion.trialUsersEver > 0 ? (conversion.converted / conversion.trialUsersEver) * 100 : null,
  };
}
