import { DevBillingProvider } from "./devBillingProvider";
import type { BillingProvider } from "./types";

export type { BillingProvider } from "./types";

let provider: BillingProvider | null = null;

/** Only one implementation exists today (DevBillingProvider) -- this is
 * the single place a future real payment processor would be swapped in. */
export function getBillingProvider(): BillingProvider {
  if (!provider) provider = new DevBillingProvider();
  return provider;
}
