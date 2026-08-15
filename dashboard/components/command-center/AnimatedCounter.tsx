"use client";

import { useEffect, useRef, useState } from "react";

const DURATION_MS = 600;

/** Subtle count-up animation for a KPI number -- animates from 0 to
 * `value` once on mount, never re-triggers on re-render with the same
 * value. Respects `prefers-reduced-motion` by snapping straight to the
 * final value (matches globals.css's own reduced-motion reset). Purely
 * cosmetic: the displayed number always ends at the real, already-
 * computed value -- nothing here recalculates anything. */
export function AnimatedCounter({ value, decimals = 0, prefix = "" }: { value: number; decimals?: number; prefix?: string }) {
  const [display, setDisplay] = useState(0);
  const startedRef = useRef(false);

  useEffect(() => {
    const reduceMotion = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    // Deferred one microtask so every setState call happens inside a
    // callback rather than the effect's synchronous body -- satisfies
    // react-hooks/set-state-in-effect (same pattern as
    // useEnvironmentSections/useVegasDisplaySettings).
    if (reduceMotion || startedRef.current) {
      Promise.resolve().then(() => setDisplay(value));
      return;
    }
    startedRef.current = true;

    const start = performance.now();
    let frame: number;
    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / DURATION_MS);
      const eased = 1 - (1 - progress) * (1 - progress); // ease-out
      setDisplay(value * eased);
      if (progress < 1) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return (
    <span>
      {prefix}
      {display.toFixed(decimals)}
    </span>
  );
}
