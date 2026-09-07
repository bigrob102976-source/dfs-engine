/** NFL public access, Phase 6 -- the optimizer (a real CP-SAT solve,
 * previously only reachable by an authenticated account) is now
 * reachable by anyone. This is the smallest real guard against
 * unbounded automated hammering: an in-memory, per-process, per-IP
 * sliding-window counter. No new dependency, no external service --
 * nfl-web runs as a single Railway instance (numReplicas: 1), so
 * in-process state is actually effective here, not just theater.
 *
 * Deliberately NOT a "giant new security system": no persistence, no
 * distributed store, no per-user tiers. If nfl-web is ever scaled to
 * multiple instances, this degrades to a per-instance limit (still
 * strictly better than no limit at all) -- upgrading to a shared store
 * at that point is a real, separate decision, not something to
 * preempt here. */

const buckets = new Map<string, number[]>();

// Bound the map itself so a flood of distinct spoofed IPs can't grow
// this forever between window expirations.
const MAX_TRACKED_KEYS = 5000;

export function checkRateLimit(key: string, maxRequests: number, windowMs: number, now: number = Date.now()): boolean {
  const existing = buckets.get(key) ?? [];
  const recent = existing.filter((t) => now - t < windowMs);

  if (recent.length >= maxRequests) {
    buckets.set(key, recent);
    return false;
  }

  recent.push(now);
  if (buckets.size >= MAX_TRACKED_KEYS && !buckets.has(key)) {
    const oldestKey = buckets.keys().next().value;
    if (oldestKey !== undefined) buckets.delete(oldestKey);
  }
  buckets.set(key, recent);
  return true;
}

/** Railway (like most platforms behind a proxy) sets x-forwarded-for to
 * "<client>, <proxy1>, <proxy2>, ..." -- the first entry is the real
 * client. Falls back to a fixed key (never throws, never blocks a
 * request) when no header is present, e.g. a direct local request. */
export function getClientIp(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  const real = request.headers.get("x-real-ip");
  if (real) return real.trim();
  return "unknown";
}

export function __resetRateLimitForTests(): void {
  buckets.clear();
}
