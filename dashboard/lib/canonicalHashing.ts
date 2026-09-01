import crypto from "node:crypto";

// M3H -- TypeScript equivalent of canonical/hashing.py::compute_normalized_hash.
// MUST produce byte-identical SHA-256 hashes to the Python implementation
// for identical canonical content -- see
// dashboard/lib/__tests__/canonicalHashing.test.ts's cross-language
// golden fixtures (hashes computed once by the real Python function,
// asserted here too) for the parity proof this exists to satisfy (M2's
// identified integrity gap: TypeScript rehydration previously could not
// independently verify an artifact's declared normalizedHash).
//
// The subtle, easy-to-get-wrong detail that makes byte-identical output
// possible: Python's json.dumps(sort_keys=True, separators=(",", ":"))
// defaults to ensure_ascii=True, which escapes every non-ASCII
// character as a \uXXXX sequence (astral characters as UTF-16 surrogate
// PAIRS, one \uXXXX escape per surrogate half). JavaScript's
// JSON.stringify does NOT do this by default. pyJsonStringify below
// replicates Python's exact escaping (and its recursive sort_keys
// behavior, since JSON.stringify has no such option) so a player name
// like "José Ramírez" serializes to the identical byte
// sequence in both languages before hashing.

/** Fields intentionally excluded from the normalizedHash payload --
 * kept in exact parity with canonical/hashing.py's
 * _VOLATILE_SLATE_FIELDS / _VOLATILE_PLAYER_FIELDS. Changing either set
 * here without changing the Python side breaks hash parity silently --
 * see this file's own test suite for the guard against that. */
const VOLATILE_SLATE_FIELDS = new Set([
  "fetchedAt", "rawHash", "normalizedHash", "retrievedAt", "validationFindings",
  "validationState", "internalSlateId", "createdAt", "updatedAt",
]);

const VOLATILE_PLAYER_FIELDS = new Set([
  "internalPlayerId", "internalSlateId", "identityStatus", "createdAt", "updatedAt",
]);

function stripVolatile(payload: Record<string, unknown>, volatileKeys: Set<string>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(payload)) {
    if (!volatileKeys.has(key)) result[key] = payload[key];
  }
  return result;
}

type Json = null | string | number | boolean | Json[] | { [key: string]: Json };

/** Mirrors canonical/hashing.py::_canonicalize: recursively sorts dict
 * keys (handled at serialization time by pyJsonStringify, not here) and
 * sorts lists of primitives (so e.g. positionEligibility=["OF","1B"]
 * and ["1B","OF"] hash the same) -- lists containing objects are left
 * in place (player ordering is normalized explicitly, keyed on
 * providerPlayerId, before this function ever sees the list). */
function canonicalize(value: Json): Json {
  if (Array.isArray(value)) {
    const items = value.map(canonicalize);
    const allPrimitive = items.length > 0 && items.every((v) => v === null || typeof v === "string" || typeof v === "number" || typeof v === "boolean");
    if (!allPrimitive) return items;
    return [...items].sort((a, b) => {
      // Mirrors Python's sorted(items, key=lambda v: (str(type(v)), v)):
      // group by type first, then compare within the same type. Every
      // real payload in this codebase produces homogeneous string
      // arrays (positionEligibility, gameIds, providerDraftableIds), so
      // this reduces to a plain string sort in practice -- true parity
      // for a genuinely mixed-type primitive array (which never occurs
      // in this schema) is not attempted, matching this module's own
      // "port the real cases, not a universal Python json emulator"
      // scope.
      const ta = typeof a;
      const tb = typeof b;
      if (ta !== tb) return ta < tb ? -1 : 1;
      if (a === b) return 0;
      return (a as string | number | boolean) < (b as string | number | boolean) ? -1 : 1;
    });
  }
  if (value !== null && typeof value === "object") {
    const result: { [key: string]: Json } = {};
    for (const key of Object.keys(value)) result[key] = canonicalize(value[key]);
    return result;
  }
  return value;
}

/** Escapes one string exactly as Python's json.dumps(ensure_ascii=True,
 * default) would -- standard JSON escapes for control characters, and
 * every character outside printable ASCII (0x20-0x7E) as \uXXXX. JS
 * strings are UTF-16 internally, so iterating charCodeAt() already
 * yields one code unit per surrogate half for astral characters --
 * exactly matching Python's own surrogate-pair escaping for the same
 * codepoints. */
function pyJsonEscapeString(value: string): string {
  let out = '"';
  for (let i = 0; i < value.length; i++) {
    const ch = value[i];
    const code = value.charCodeAt(i);
    if (ch === '"') out += '\\"';
    else if (ch === "\\") out += "\\\\";
    else if (code === 0x08) out += "\\b";
    else if (code === 0x0c) out += "\\f";
    else if (code === 0x0a) out += "\\n";
    else if (code === 0x0d) out += "\\r";
    else if (code === 0x09) out += "\\t";
    else if (code < 0x20 || code > 0x7e) out += "\\u" + code.toString(16).padStart(4, "0");
    else out += ch;
  }
  return out + '"';
}

/** Serializes `value` to JSON text byte-identical to Python's
 * json.dumps(value, sort_keys=True, separators=(",", ":")) would
 * produce for the same logical content -- recursively sorted object
 * keys, no whitespace, ensure_ascii-style string escaping. */
export function pyJsonStringify(value: Json): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error(`Cannot serialize non-finite number: ${value}`);
    return String(value);
  }
  if (typeof value === "string") return pyJsonEscapeString(value);
  if (Array.isArray(value)) return "[" + value.map(pyJsonStringify).join(",") + "]";
  if (typeof value === "object") {
    const keys = Object.keys(value).sort();
    return "{" + keys.map((k) => pyJsonEscapeString(k) + ":" + pyJsonStringify((value as Record<string, Json>)[k])).join(",") + "}";
  }
  throw new Error(`Cannot serialize value of type ${typeof value}`);
}

export function buildNormalizedHashPayload(
  slate: Record<string, unknown>, players: Array<Record<string, unknown>>,
): { slate: Json; players: Json[] } {
  const slateContent = stripVolatile(slate, VOLATILE_SLATE_FIELDS);
  const playerContents = players.map((p) => stripVolatile(p, VOLATILE_PLAYER_FIELDS));
  playerContents.sort((a, b) => {
    const pa = String(a.providerPlayerId ?? "");
    const pb = String(b.providerPlayerId ?? "");
    return pa < pb ? -1 : pa > pb ? 1 : 0;
  });
  return {
    slate: canonicalize(slateContent as Json),
    players: playerContents.map((p) => canonicalize(p as Json)),
  };
}

/** TypeScript equivalent of canonical/hashing.py::compute_normalized_hash.
 * `slate`/`players` are plain objects matching CanonicalSlateDocument /
 * CanonicalSlatePlayerDocument's camelCase shape (canonicalArtifact.ts)
 * -- the SAME shape the artifact document already carries, so a caller
 * can pass `artifact.slate` / `artifact.players` directly. */
export function computeNormalizedHash(slate: Record<string, unknown>, players: Array<Record<string, unknown>>): string {
  const payload = buildNormalizedHashPayload(slate, players);
  const canonicalJson = pyJsonStringify(payload);
  return crypto.createHash("sha256").update(canonicalJson, "utf-8").digest("hex");
}

/** TypeScript equivalent of canonical/hashing.py::compute_raw_hash --
 * SHA-256 of exact bytes, lowercase hex. */
export function computeRawHash(rawBytes: Buffer): string {
  return crypto.createHash("sha256").update(rawBytes).digest("hex");
}
