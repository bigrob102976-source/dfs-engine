// Every browser-supplied slateId passes through this before it can ever
// reach a Python subprocess argv (spawn is already shell:false, so
// injection isn't possible regardless of content -- see
// lib/orchestrator/pythonRunner.ts -- but a generic safe-token shape
// check is cheap defense-in-depth against unexpected garbage reaching
// the provider layer).
const SAFE_SLATE_ID = /^[A-Za-z0-9_.:-]{1,128}$/;

export function isValidSlateId(value: unknown): value is string {
  return typeof value === "string" && SAFE_SLATE_ID.test(value);
}
