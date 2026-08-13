/** Several scripts (list_dfs_slates.py, optimize_dk_lineups.py --validate-only)
 * print exactly one line of JSON as their machine-readable output, but
 * Python may also emit warnings/deprecation notices on stdout before it --
 * scan from the end so the last valid JSON line wins regardless. */
export function parseLastJsonLine(stdout: string): Record<string, unknown> | null {
  const lines = stdout.trim().split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      return JSON.parse(lines[i]);
    } catch {
      continue;
    }
  }
  return null;
}
