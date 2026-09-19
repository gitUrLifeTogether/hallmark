/* The headline, as two pairs of bars.
 *
 * The heatmap beside this is the honest record — twenty-four scenarios, one cell each, so
 * a reader can find the one that went differently. But a grid of twenty-four cells does
 * not answer "did it work" at a glance, and that is the first question anyone asks.
 *
 * Utility is shown next to attack success on purpose. A system that refused everything
 * would score zero on attacks and be worthless, so the two numbers only mean something
 * together; showing the good one alone would be the easiest way to mislead with a true
 * figure.
 */

import { BENCH_SUMMARY } from "../lib/benchData";

interface Bar {
  config: string;
  asr: number;
  utility: number;
}

const BARS: Bar[] = [
  {
    config: "Unprotected agent",
    asr: BENCH_SUMMARY.baselineAsr,
    utility: BENCH_SUMMARY.baselineUtility,
  },
  {
    config: "With Hallmark",
    asr: BENCH_SUMMARY.hallmarkAsr,
    utility: BENCH_SUMMARY.hallmarkUtility,
  },
];

const WIDTH = 520;
const HEIGHT = 208;
const LEFT = 122;
const RIGHT = 56;
const TOP = 26;
const BAR_HEIGHT = 20;
const GAP = 10;
const GROUP_GAP = 34;

const PLOT = WIDTH - LEFT - RIGHT;

export function BenchBars() {
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div
        style={{
          display: "flex",
          gap: 18,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <h3 style={{ margin: 0, fontSize: 17, fontWeight: 600 }}>
          Attacks stopped, work still done
        </h3>
        <Legend colour="var(--deny)" label="Attacks that succeeded" />
        <Legend colour="var(--allow)" label="Legitimate invoices still paid" />
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        role="img"
        aria-label={
          `Unprotected agent: ${Math.round(BENCH_SUMMARY.baselineAsr * 100)}% of attacks succeeded, ` +
          `${Math.round(BENCH_SUMMARY.baselineUtility * 100)}% utility. ` +
          `With Hallmark: ${Math.round(BENCH_SUMMARY.hallmarkAsr * 100)}% of attacks succeeded, ` +
          `${Math.round(BENCH_SUMMARY.hallmarkUtility * 100)}% utility.`
        }
        style={{ fontFamily: "var(--font-ui)", maxWidth: 560 }}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <g key={tick}>
            <line
              x1={LEFT + tick * PLOT}
              y1={TOP - 8}
              x2={LEFT + tick * PLOT}
              y2={HEIGHT - 26}
              stroke="var(--rule)"
              strokeWidth={1}
            />
            <text
              x={LEFT + tick * PLOT}
              y={HEIGHT - 10}
              textAnchor="middle"
              fontSize="11"
              fill="var(--ink-3)"
            >
              {Math.round(tick * 100)}%
            </text>
          </g>
        ))}

        {BARS.map((bar, index) => {
          const groupTop = TOP + index * (BAR_HEIGHT * 2 + GAP + GROUP_GAP);
          return (
            <g key={bar.config}>
              <text
                x={LEFT - 12}
                y={groupTop + BAR_HEIGHT + 2}
                textAnchor="end"
                fontSize="13"
                fontWeight="600"
                fill="var(--ink)"
              >
                {bar.config}
              </text>

              <BarRow
                y={groupTop}
                value={bar.asr}
                colour="var(--deny)"
                // Zero needs to read as a deliberate measurement rather than a missing
                // bar, so it keeps a visible stub and its label sits outside.
                label={`${Math.round(bar.asr * 100)}%`}
              />
              <BarRow
                y={groupTop + BAR_HEIGHT + GAP}
                value={bar.utility}
                colour="var(--allow)"
                label={`${Math.round(bar.utility * 100)}%`}
              />
            </g>
          );
        })}
      </svg>

      <p
        style={{
          margin: 0,
          fontSize: 13,
          color: "var(--ink-2)",
          maxWidth: "62ch",
        }}
      >
        {BENCH_SUMMARY.scenarios} scenarios, measured {BENCH_SUMMARY.measuredOn}
        . Both runs are deterministic, so these figures describe the enforcement
        layer rather than how a language model behaves.
      </p>
    </div>
  );
}

function BarRow({
  y,
  value,
  colour,
  label,
}: {
  y: number;
  value: number;
  colour: string;
  label: string;
}) {
  const width = Math.max(value * PLOT, 2);
  return (
    <g>
      <rect
        x={LEFT}
        y={y}
        width={PLOT}
        height={BAR_HEIGHT}
        fill="var(--surface-2)"
        rx={3}
      />
      <rect
        x={LEFT}
        y={y}
        width={width}
        height={BAR_HEIGHT}
        fill={colour}
        rx={3}
      />
      <text
        x={LEFT + width + 8}
        y={y + BAR_HEIGHT - 5}
        fontSize="12"
        fontWeight="600"
        fill="var(--ink)"
      >
        {label}
      </text>
    </g>
  );
}

function Legend({ colour, label }: { colour: string; label: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 13,
      }}
    >
      <span
        aria-hidden
        style={{ width: 11, height: 11, borderRadius: 2, background: colour }}
      />
      <span style={{ color: "var(--ink-2)" }}>{label}</span>
    </span>
  );
}
