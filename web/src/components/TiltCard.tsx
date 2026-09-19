/* A card that leans toward the cursor.
 *
 * The effect is deliberately small — four degrees at the corners — because the console's
 * subject is evidence and evidence should not bounce. What it buys is the sense of
 * handling something physical: the card has a near edge and a far one, and which is which
 * follows your hand.
 *
 * Under prefers-reduced-motion nothing rotates at all. That is not a downgrade to be
 * apologised for: the resting shadow and the hover shadow carry the same information, and
 * a surface that tilts under the pointer is exactly the movement some people cannot
 * tolerate.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

const MAX_DEGREES = 4;

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    // Older engines and locked-down contexts both land here. Assume the cautious answer.
    return true;
  }
}

/** Tracks the media query, so a change of setting takes effect without a reload. */
function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(prefersReducedMotion);

  useEffect(() => {
    let query: MediaQueryList;
    try {
      query = window.matchMedia("(prefers-reduced-motion: reduce)");
    } catch {
      return;
    }
    const onChange = () => setReduced(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

export function TiltCard({
  children,
  style,
  className = "",
  elevation = "var(--shadow-1)",
  as: Tag = "div",
}: {
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
  /** Resting elevation. Hover lifts to --shadow-3 via the .hm-tilt rule. */
  elevation?: string;
  as?: "div" | "article" | "section";
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const [transform, setTransform] = useState("");

  const onPointerMove = useCallback(
    (event: React.PointerEvent) => {
      if (reduced || !ref.current) return;
      const box = ref.current.getBoundingClientRect();

      // Position within the card, as -0.5 … 0.5 from its centre.
      const x = (event.clientX - box.left) / box.width - 0.5;
      const y = (event.clientY - box.top) / box.height - 0.5;

      // Y drives rotateX and X drives rotateY: pointing at the top edge tips the top away.
      setTransform(
        `perspective(900px) rotateX(${(-y * MAX_DEGREES * 2).toFixed(2)}deg) ` +
          `rotateY(${(x * MAX_DEGREES * 2).toFixed(2)}deg)`,
      );
    },
    [reduced],
  );

  const settle = useCallback(() => setTransform(""), []);

  return (
    <Tag
      ref={ref as never}
      className={`hm-tilt ${className}`.trim()}
      onPointerMove={onPointerMove}
      onPointerLeave={settle}
      onBlur={settle}
      style={{ boxShadow: elevation, transform, ...style }}
    >
      {children}
    </Tag>
  );
}
