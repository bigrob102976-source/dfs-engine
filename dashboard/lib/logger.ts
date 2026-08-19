// Milestone 30: structured server-side logging -- one JSON line per
// event to stdout/stderr (the standard "logs are just structured stdout"
// contract every hosting platform's log aggregator expects; no vendor
// chosen). Fields are the ones this milestone's spec names explicitly:
// requestId/jobId/slateId/slateDate/operation/durationMs/status. Never
// logs a password, token, API key, or other secret -- see
// SENSITIVE_KEY_PATTERN below, applied to every field key regardless of
// caller intent.

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface LogFields {
  requestId?: string;
  jobId?: string;
  slateId?: string;
  slateDate?: string;
  operation?: string;
  durationMs?: number;
  status?: string;
  userId?: string;
  [key: string]: unknown;
}

const SENSITIVE_KEY_PATTERN = /password|token|secret|api[_-]?key|authorization|cookie|credential/i;

export function redactFields(fields: LogFields): LogFields {
  const out: LogFields = {};
  for (const [key, value] of Object.entries(fields)) {
    out[key] = SENSITIVE_KEY_PATTERN.test(key) ? "[REDACTED]" : value;
  }
  return out;
}

export interface LogEntry extends LogFields {
  timestamp: string;
  level: LogLevel;
  message: string;
}

export function log(level: LogLevel, message: string, fields: LogFields = {}): LogEntry {
  const entry: LogEntry = { timestamp: new Date().toISOString(), level, message, ...redactFields(fields) };
  const line = JSON.stringify(entry);
  if (level === "error") console.error(line);
  else if (level === "warn") console.warn(line);
  else console.log(line);
  return entry;
}

export const logger = {
  debug: (message: string, fields?: LogFields) => log("debug", message, fields),
  info: (message: string, fields?: LogFields) => log("info", message, fields),
  warn: (message: string, fields?: LogFields) => log("warn", message, fields),
  error: (message: string, fields?: LogFields) => log("error", message, fields),
};
