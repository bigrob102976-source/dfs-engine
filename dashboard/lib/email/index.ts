import { DevEmailAdapter } from "./devEmailAdapter";
import type { EmailAdapter } from "./types";

export type { EmailAdapter } from "./types";

let adapter: EmailAdapter | null = null;

/** Only one implementation exists today (DevEmailAdapter) -- this is
 * the single place a future real provider would be swapped in. */
export function getEmailAdapter(): EmailAdapter {
  if (!adapter) adapter = new DevEmailAdapter();
  return adapter;
}
