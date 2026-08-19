import { logger, type LogFields } from "./logger";

// Milestone 30: a clean, minimal seam for future hosted error monitoring
// (Sentry, Bugsnag, etc.) -- no vendor is chosen or paid for in this
// milestone (per its explicit scope). captureError() currently just logs
// a structured "error" line via lib/logger.ts; wiring a real vendor SDK
// later is a one-function change here, not a hunt through every catch
// block in the codebase that already calls this.

export function captureError(error: unknown, context: LogFields = {}): void {
  const message = error instanceof Error ? error.message : String(error);
  const stack = error instanceof Error ? error.stack : undefined;
  logger.error(message, { ...context, stack });
}
