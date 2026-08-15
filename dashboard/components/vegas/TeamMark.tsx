/** Lightweight placeholder "logo" -- a colored circular team-abbreviation
 * mark. This project has no team-logo image assets and no icon library
 * dependency to fetch them from, so a deterministic-per-team colored
 * initial is the honest stand-in (never an invented/fetched image). */
function hashHue(team: string): number {
  let hash = 0;
  for (let i = 0; i < team.length; i++) hash = (hash * 31 + team.charCodeAt(i)) % 360;
  return hash;
}

export function TeamMark({ team, size = 22 }: { team: string; size?: number }) {
  const hue = hashHue(team);
  return (
    <span
      aria-hidden="true"
      className="inline-flex shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-white"
      style={{ width: size, height: size, backgroundColor: `hsl(${hue}, 45%, 32%)` }}
    >
      {team.slice(0, 2)}
    </span>
  );
}
