/* The same inbox, processed twice, side by side.
 *
 * Left is an agent with no enforcement layer. Right is the same agent behind one. They
 * agree on sixteen invoices and disagree on three, and the disagreements are the point.
 *
 * Both columns come from recorded runs rather than being re-simulated here. The console
 * must not contain a second implementation of the rules, because a second implementation
 * eventually disagrees with the one that decides.
 */

import { useState } from "react";
import { COMPARISON, type ComparisonRow } from "../lib/comparisonData";
import { formatPaise } from "../lib/types";

function Cell({
  outcome,
  detail,
  tone,
}: {
  outcome: string;
  detail: string;
  tone: "paid" | "held" | "blocked" | "stolen";
}) {
  const colour =
    tone === "paid"
      ? "var(--allow)"
      : tone === "held"
        ? "var(--pending)"
        : tone === "stolen"
          ? "var(--deny)"
          : "var(--deny)";

  return (
    <div
      style={{
        display: "grid",
        gap: 2,
        padding: "8px 10px",
        borderRadius: "var(--radius-sm)",
        border: `1px solid ${colour}`,
        // The stolen payment is the only cell that is filled rather than outlined.
        // It should be the thing the eye lands on.
        background: tone === "stolen" ? "var(--untrusted-soft)" : "transparent",
        backgroundImage: tone === "stolen" ? "var(--hatch)" : "none",
      }}
    >
      <strong style={{ fontSize: 12, color: colour, letterSpacing: "0.03em" }}>
        {outcome}
      </strong>
      <span style={{ fontSize: 12, color: "var(--ink-2)" }}>{detail}</span>
    </div>
  );
}

export function SplitReplay() {
  const [step, setStep] = useState(COMPARISON.length);
  const visible = COMPARISON.slice(0, step);

  const stolen = visible
    .filter((r) => r.unprotected.tone === "stolen")
    .reduce((sum, r) => sum + r.amountPaise, 0);
  const unprotectedPaid = visible
    .filter(
      (r) => r.unprotected.tone === "paid" || r.unprotected.tone === "stolen",
    )
    .reduce((sum, r) => sum + r.amountPaise, 0);
  const protectedPaid = visible
    .filter((r) => r.protectedRun.tone === "paid")
    .reduce((sum, r) => sum + r.amountPaise, 0);

  return (
    <section style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "grid", gap: 6 }}>
        <h2 style={{ margin: 0, fontSize: 21, fontWeight: 600 }}>
          The same inbox, twice
        </h2>
        <p
          style={{
            margin: 0,
            color: "var(--ink-2)",
            fontSize: 14,
            maxWidth: 700,
          }}
        >
          Same agent, same supplier systems, same twenty emails. The only
          difference is whether a policy sees where each argument came from
          before the money moves.
        </p>
      </div>

      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <label htmlFor="replay" style={{ fontSize: 13, color: "var(--ink-2)" }}>
          Replay to email {step} of {COMPARISON.length}
        </label>
        <input
          id="replay"
          type="range"
          min={0}
          max={COMPARISON.length}
          value={step}
          onChange={(event) => setStep(Number(event.target.value))}
          style={{ flex: "1 1 240px" }}
        />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          background: "var(--surface)",
          border: "1px solid var(--rule)",
          borderRadius: "var(--radius-lg)",
          padding: 16,
        }}
      >
        <div style={{ display: "grid", gap: 4 }}>
          <span style={{ fontSize: 12, color: "var(--ink-2)" }}>
            Unprotected agent
          </span>
          <strong
            className="tabular"
            style={{
              fontSize: 24,
              color: stolen ? "var(--deny)" : "var(--ink)",
            }}
          >
            {formatPaise(unprotectedPaid)}
          </strong>
          <span style={{ fontSize: 12, color: "var(--deny)" }}>
            {stolen > 0
              ? `${formatPaise(stolen)} to an attacker`
              : "nothing lost yet"}
          </span>
        </div>
        <div style={{ display: "grid", gap: 4 }}>
          <span style={{ fontSize: 12, color: "var(--ink-2)" }}>
            With Hallmark
          </span>
          <strong className="tabular" style={{ fontSize: 24 }}>
            {formatPaise(protectedPaid)}
          </strong>
          <span style={{ fontSize: 12, color: "var(--allow)" }}>
            nothing to an attacker
          </span>
        </div>
      </div>

      <table
        style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}
      >
        <thead>
          <tr
            style={{ textAlign: "left", color: "var(--ink-3)", fontSize: 12 }}
          >
            <th style={{ padding: "6px 8px", fontWeight: 600 }}>Email</th>
            <th style={{ padding: "6px 8px", fontWeight: 600 }}>Unprotected</th>
            <th style={{ padding: "6px 8px", fontWeight: 600 }}>
              With Hallmark
            </th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row: ComparisonRow) => (
            <tr
              key={row.emailId}
              style={{ borderTop: "1px solid var(--rule)" }}
            >
              <td
                style={{
                  padding: "8px",
                  verticalAlign: "top",
                  whiteSpace: "nowrap",
                }}
              >
                <code className="mono" style={{ fontSize: 12 }}>
                  {row.emailId}
                </code>
                <div style={{ fontSize: 11, color: "var(--ink-3)" }}>
                  {row.label}
                </div>
              </td>
              <td style={{ padding: "8px", verticalAlign: "top" }}>
                <Cell {...row.unprotected} />
              </td>
              <td style={{ padding: "8px", verticalAlign: "top" }}>
                <Cell {...row.protectedRun} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p style={{ margin: 0, fontSize: 13, color: "var(--ink-3)" }}>
        Both columns are recorded outcomes from deterministic runs over the same
        fixture, not a simulation in this page.
      </p>
    </section>
  );
}
