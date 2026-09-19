/* The journey one email takes, drawn in the same language as the lineage graph.
 *
 * Hatched means the step is handling untrusted content; solid means it is working from
 * company records or code. That is the identical rule the ProvenanceTag and LineageGraph
 * use, and reusing it here is the point: someone who learns to read hatching on this
 * diagram can already read it everywhere else in the console.
 *
 * The sequence can be played, because the order is the argument. Reading the shape alone
 * does not show that the reader sees the text and the planner never does; watching the
 * untrusted path stop at the enforcement point does.
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface Step {
  id: string;
  label: string;
  detail: string;
  /** Hatched when this step handles attacker-controlled content. */
  untrusted: boolean;
  column: number;
  row: number;
}

const STEPS: Step[] = [
  {
    id: "request",
    label: "User request",
    detail: "Ananya asks for this week's invoices to be paid.",
    untrusted: false,
    column: 0,
    row: 1,
  },
  {
    id: "mandate",
    label: "Mandate",
    detail:
      "Turned into a scope with caps, and confirmed by her before anything runs.",
    untrusted: false,
    column: 1,
    row: 1,
  },
  {
    id: "inbox",
    label: "Email",
    detail: "Arrives from outside. Anything in it may be an instruction.",
    untrusted: true,
    column: 2,
    row: 0,
  },
  {
    id: "reader",
    label: "Reader",
    detail:
      "Reads the text and has no tools. Assume it can be fooled completely.",
    untrusted: true,
    column: 3,
    row: 0,
  },
  {
    id: "values",
    label: "Labelled values",
    detail:
      "Each carries where it came from. Labels only ever join, never subtract.",
    untrusted: true,
    column: 4,
    row: 0,
  },
  {
    id: "planner",
    label: "Planner",
    detail: "Holds the tools, names values by handle, never sees the text.",
    untrusted: false,
    column: 3,
    row: 2,
  },
  {
    id: "vendor",
    label: "Vendor master",
    detail: "The company's own record of who is paid, and to which account.",
    untrusted: false,
    column: 4,
    row: 2,
  },
  {
    id: "pep",
    label: "Enforcement point",
    detail:
      "Resolves every handle, computes the facts in code, then asks the policy.",
    untrusted: false,
    column: 5,
    row: 1,
  },
  {
    id: "cedar",
    label: "Cedar decides",
    detail: "Not just what the agent is doing — where each argument came from.",
    untrusted: false,
    column: 6,
    row: 1,
  },
  {
    id: "outcome",
    label: "Executed · Held · Blocked",
    detail: "And a lineage record, so why is a query rather than an argument.",
    untrusted: false,
    column: 7,
    row: 1,
  },
];

const EDGES: [string, string][] = [
  ["request", "mandate"],
  ["mandate", "planner"],
  ["inbox", "reader"],
  ["reader", "values"],
  ["values", "pep"],
  ["planner", "vendor"],
  ["vendor", "pep"],
  ["pep", "cedar"],
  ["cedar", "outcome"],
];

const COLUMN_WIDTH = 132;
const ROW_HEIGHT = 96;
const BOX_WIDTH = 112;
const BOX_HEIGHT = 52;
const PADDING = 16;

const WIDTH = PADDING * 2 + COLUMN_WIDTH * 7 + BOX_WIDTH;
const HEIGHT = PADDING * 2 + ROW_HEIGHT * 2 + BOX_HEIGHT;

function position(step: Step) {
  return {
    x: PADDING + step.column * COLUMN_WIDTH,
    y: PADDING + step.row * ROW_HEIGHT,
  };
}

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return true;
  }
}

export function LifecycleDiagram() {
  const [revealed, setRevealed] = useState<number>(0);
  const [playing, setPlaying] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<number | undefined>(undefined);

  const showAll = useCallback(() => {
    setRevealed(STEPS.length);
    setPlaying(false);
  }, []);

  const play = useCallback(() => {
    if (prefersReducedMotion()) {
      showAll();
      return;
    }
    window.clearInterval(timerRef.current);
    setRevealed(0);
    setPlaying(true);
    timerRef.current = window.setInterval(() => {
      setRevealed((n) => {
        if (n >= STEPS.length) {
          window.clearInterval(timerRef.current);
          setPlaying(false);
          return n;
        }
        return n + 1;
      });
    }, 320);
  }, [showAll]);

  // Play once when the diagram is first scrolled to. Someone who arrives mid-page should
  // see the sequence rather than a finished picture they have to work backwards from.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    if (prefersReducedMotion() || typeof IntersectionObserver === "undefined") {
      showAll();
      return;
    }

    let played = false;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && !played) {
            played = true;
            play();
          }
        }
      },
      { threshold: 0.35 },
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      window.clearInterval(timerRef.current);
    };
  }, [play, showAll]);

  const indexOf = new Map(STEPS.map((step, index) => [step.id, index]));

  return (
    <div ref={containerRef} style={{ display: "grid", gap: 12 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <h3 style={{ margin: 0, fontSize: 17, fontWeight: 600 }}>
          What happens to one email
        </h3>
        <button type="button" onClick={play} disabled={playing}>
          {playing ? "Playing…" : "Play the sequence"}
        </button>
        <span style={{ fontSize: 13, color: "var(--ink-2)" }}>
          Hatched steps are handling content an attacker controls.
        </span>
      </div>

      <div style={{ overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          width="100%"
          role="img"
          aria-label="An email is read by the reader, labelled, and every payment argument is checked by the enforcement point before Cedar decides."
          style={{ minWidth: 720, fontFamily: "var(--font-ui)" }}
        >
          <defs>
            {/* The same texture, the same angle and the same weight as the lineage graph
             * and the provenance tags. One rule, learned once. */}
            <pattern
              id="lifecycle-hatch"
              patternUnits="userSpaceOnUse"
              width="7"
              height="7"
              patternTransform="rotate(135)"
            >
              <rect width="7" height="7" fill="var(--untrusted-soft)" />
              <line
                x1="0"
                y1="0"
                x2="0"
                y2="7"
                stroke="var(--untrusted)"
                strokeWidth="2"
                opacity="0.35"
              />
            </pattern>
            <marker
              id="lifecycle-arrow"
              markerWidth="9"
              markerHeight="9"
              refX="8"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L0,6 L8,3 z" fill="var(--ink-3)" />
            </marker>
          </defs>

          {EDGES.map(([fromId, toId]) => {
            const from = STEPS.find((s) => s.id === fromId);
            const to = STEPS.find((s) => s.id === toId);
            if (!from || !to) return null;
            const a = position(from);
            const b = position(to);
            const visible = revealed > (indexOf.get(toId) ?? 0);

            const x1 = a.x + BOX_WIDTH;
            const y1 = a.y + BOX_HEIGHT / 2;
            const x2 = b.x;
            const y2 = b.y + BOX_HEIGHT / 2;
            const midX = (x1 + x2) / 2;

            return (
              <path
                key={`${fromId}-${toId}`}
                d={`M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}`}
                fill="none"
                stroke="var(--ink-3)"
                strokeWidth={1.5}
                markerEnd="url(#lifecycle-arrow)"
                opacity={visible ? 0.75 : 0.12}
                style={{ transition: "opacity 300ms ease" }}
              />
            );
          })}

          {STEPS.map((step, index) => {
            const { x, y } = position(step);
            const visible = revealed > index;
            return (
              <g
                key={step.id}
                opacity={visible ? 1 : 0.22}
                style={{ transition: "opacity 300ms ease" }}
              >
                <title>{step.detail}</title>
                <rect
                  x={x}
                  y={y}
                  width={BOX_WIDTH}
                  height={BOX_HEIGHT}
                  rx={8}
                  fill={
                    step.untrusted
                      ? "url(#lifecycle-hatch)"
                      : "var(--surface-2)"
                  }
                  stroke={
                    step.untrusted ? "var(--untrusted)" : "var(--trusted)"
                  }
                  strokeWidth={1.5}
                />
                <text
                  x={x + BOX_WIDTH / 2}
                  y={y + BOX_HEIGHT / 2 + 4}
                  textAnchor="middle"
                  fontSize="12"
                  fontWeight="600"
                  fill="var(--ink)"
                >
                  {step.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <ol
        style={{
          margin: 0,
          paddingLeft: 20,
          fontSize: 14,
          color: "var(--ink-2)",
        }}
      >
        {STEPS.map((step, index) => (
          <li
            key={step.id}
            style={{
              marginBottom: 2,
              opacity: revealed > index ? 1 : 0.45,
              transition: "opacity 300ms ease",
            }}
          >
            <strong style={{ color: "var(--ink)", fontWeight: 600 }}>
              {step.label}
            </strong>
            {" — "}
            {step.detail}
          </li>
        ))}
      </ol>
    </div>
  );
}
