/* The attack bench, as measured.
 *
 * A grid of scenarios against configurations. Cells carry a word as well as a colour,
 * because a heatmap that only encodes outcome in hue is unreadable to some people and
 * useless in a greyscale screenshot.
 *
 * The caveats are on this page rather than in a footnote elsewhere. A number without its
 * limits invites a reading the measurement does not support, and the most important thing
 * this grid does not measure is model behaviour: both runs are deterministic.
 */

import { BENCH_ROWS, BENCH_SUMMARY, type BenchRow } from "../lib/benchData";

function Outcome({ succeeded }: { succeeded: boolean }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 9px",
        borderRadius: "var(--radius-sm)",
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.03em",
        color: succeeded ? "var(--deny)" : "var(--allow)",
        border: `1px solid ${succeeded ? "var(--deny)" : "var(--allow)"}`,
        background: succeeded ? "var(--untrusted-soft)" : "transparent",
        backgroundImage: succeeded ? "var(--hatch)" : "none",
      }}
    >
      {succeeded ? "SUCCEEDED" : "BLOCKED"}
    </span>
  );
}

export function Bench() {
  const byClass = new Map<string, BenchRow[]>();
  for (const row of BENCH_ROWS) {
    byClass.set(row.classLabel, [...(byClass.get(row.classLabel) ?? []), row]);
  }

  return (
    <section style={{ display: "grid", gap: 18 }}>
      <div style={{ display: "grid", gap: 6 }}>
        <h2 style={{ margin: 0, fontSize: 21, fontWeight: 600 }}>
          Attack bench
        </h2>
        <p
          style={{
            margin: 0,
            color: "var(--ink-2)",
            fontSize: 14,
            maxWidth: 700,
          }}
        >
          {BENCH_SUMMARY.scenarios} scenarios across eight attack classes,
          measured {BENCH_SUMMARY.measuredOn}. Success means money reached the
          attacker or company records left the company — never what the agent
          said about it.
        </p>
      </div>

      <div
        style={{
          display: "flex",
          gap: 36,
          flexWrap: "wrap",
          background: "var(--surface)",
          border: "1px solid var(--rule)",
          borderRadius: "var(--radius-lg)",
          padding: 18,
        }}
      >
        <div style={{ display: "grid", gap: 2 }}>
          <span
            className="tabular"
            style={{ fontSize: 28, color: "var(--deny)" }}
          >
            {Math.round(BENCH_SUMMARY.baselineAsr * 100)}%
          </span>
          <span style={{ fontSize: 12, color: "var(--ink-2)" }}>
            attacks succeed, unprotected
          </span>
        </div>
        <div style={{ display: "grid", gap: 2 }}>
          <span
            className="tabular"
            style={{ fontSize: 28, color: "var(--allow)" }}
          >
            {Math.round(BENCH_SUMMARY.hallmarkAsr * 100)}%
          </span>
          <span style={{ fontSize: 12, color: "var(--ink-2)" }}>
            with Hallmark
          </span>
        </div>
        <div style={{ display: "grid", gap: 2 }}>
          <span className="tabular" style={{ fontSize: 28 }}>
            {Math.round(BENCH_SUMMARY.hallmarkUtility * 100)}%
          </span>
          <span style={{ fontSize: 12, color: "var(--ink-2)" }}>
            legitimate invoices still paid
          </span>
        </div>
      </div>

      {[...byClass.entries()].map(([label, rows]) => (
        <div key={label} style={{ display: "grid", gap: 6 }}>
          <strong style={{ fontSize: 14 }}>{label}</strong>
          <table
            style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}
          >
            <thead>
              <tr
                style={{
                  textAlign: "left",
                  color: "var(--ink-3)",
                  fontSize: 11,
                }}
              >
                <th style={{ padding: "4px 8px", fontWeight: 600 }}>
                  Scenario
                </th>
                <th style={{ padding: "4px 8px", fontWeight: 600 }}>
                  Unprotected
                </th>
                <th style={{ padding: "4px 8px", fontWeight: 600 }}>
                  With Hallmark
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.scenarioId}
                  style={{ borderTop: "1px solid var(--rule)" }}
                >
                  <td style={{ padding: "8px", verticalAlign: "top" }}>
                    <code className="mono" style={{ fontSize: 12 }}>
                      {row.scenarioId}
                    </code>
                    <div style={{ fontSize: 11, color: "var(--ink-3)" }}>
                      {row.description}
                    </div>
                  </td>
                  <td style={{ padding: "8px", verticalAlign: "top" }}>
                    <Outcome succeeded={row.baselineSucceeded} />
                  </td>
                  <td style={{ padding: "8px", verticalAlign: "top" }}>
                    <Outcome succeeded={row.hallmarkSucceeded} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      <div
        style={{
          border: "1px solid var(--rule)",
          borderRadius: "var(--radius-md)",
          padding: 16,
          display: "grid",
          gap: 8,
        }}
      >
        <strong style={{ fontSize: 14 }}>What this does not measure</strong>
        <ul
          style={{
            margin: 0,
            paddingLeft: 18,
            color: "var(--ink-2)",
            fontSize: 13,
          }}
        >
          <li>
            Both runs are deterministic. These figures isolate the enforcement
            layer and say nothing about how a language model behaves.
          </li>
          <li>
            The baseline is obedient, not careless: it pays every legitimate
            invoice correctly and was not weakened for the comparison.
          </li>
          <li>
            Availability is not counted. An attacker who only gets invoices
            flagged has still cost somebody time.
          </li>
          <li>
            One tenant and one fixture company. Nothing here covers a different
            vendor master or mandate.
          </li>
        </ul>
      </div>
    </section>
  );
}
