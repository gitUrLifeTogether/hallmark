/* One enforcement decision, with the provenance of every argument.
 *
 * The argument table is the point of the whole console: it puts each value next to where it
 * came from, so a reader can see that the refusal follows from provenance rather than from
 * anything the model said or did.
 *
 * Policies that no approver can lift are marked as such. "Blocked" and "blocked unless
 * someone signs it off" are very different facts for the person reading this, and showing
 * them identically would be misleading in the direction that matters.
 */

import { ProvenanceTag } from "../ProvenanceTag";
import { TiltCard } from "./TiltCard";
import { POLICIES } from "../lib/demoData";
import type { Decision } from "../lib/types";

const VERDICT_LABEL: Record<Decision["outcome"], string> = {
  EXECUTED: "EXECUTED",
  PENDING_APPROVAL: "NEEDS APPROVAL",
  DENIED: "BLOCKED",
};

const VERDICT_COLOUR: Record<Decision["outcome"], string> = {
  EXECUTED: "var(--allow)",
  PENDING_APPROVAL: "var(--pending)",
  DENIED: "var(--deny)",
};

function VerdictStamp({ outcome }: { outcome: Decision["outcome"] }) {
  return (
    <span
      className="hm-stamp hm-seal"
      style={{
        fontFamily: "var(--font-display)",
        fontSize: 17,
        letterSpacing: "0.06em",
        padding: "3px 14px",
        display: "inline-block",
        transform: "rotate(-2deg)",
        color: VERDICT_COLOUR[outcome],
        border: `2px solid ${VERDICT_COLOUR[outcome]}`,
        // A hallmark is struck into silver, and this is the moment the console is named
        // after. The metallic note appears here and on a completed review, nowhere else:
        // spend it anywhere and it stops meaning "this was stamped".
        outline: "1px solid var(--accent-gold)",
        outlineOffset: 2,
        borderRadius: "var(--radius-sm)",
        whiteSpace: "nowrap",
      }}
    >
      {VERDICT_LABEL[outcome]}
    </span>
  );
}

export function DecisionCard({
  decision,
  onShowLineage,
}: {
  decision: Decision;
  onShowLineage?: (decisionId: string) => void;
}) {
  const entries = Object.entries(decision.args);

  return (
    <TiltCard
      as="article"
      elevation="var(--shadow-2)"
      className="hm-card"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--rule)",
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-1)",
        padding: 20,
        display: "grid",
        gap: 16,
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <code className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
            {decision.tool}
          </code>
          <span style={{ color: "var(--ink-3)", marginLeft: 8, fontSize: 13 }}>
            {decision.emailId}
          </span>
        </div>
        <VerdictStamp outcome={decision.outcome} />
      </header>

      {/* A narrow screen scrolls the table rather than the page. */}
      <div style={{ overflowX: "auto" }}>
        <table
          style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}
        >
          <caption
            style={{
              captionSide: "top",
              textAlign: "left",
              fontSize: 12,
              color: "var(--ink-2)",
              paddingBottom: 6,
            }}
          >
            Arguments, and where each one came from
          </caption>
          <thead>
            <tr
              style={{ textAlign: "left", color: "var(--ink-3)", fontSize: 12 }}
            >
              <th style={{ padding: "4px 0", fontWeight: 600 }}>Argument</th>
              <th style={{ padding: "4px 0", fontWeight: 600 }}>Value</th>
              <th style={{ padding: "4px 0", fontWeight: 600 }}>Provenance</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([name, value]) => (
              <tr key={name} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={{ padding: "8px 0", color: "var(--ink-2)" }}>
                  {name}
                </td>
                <td style={{ padding: "8px 0" }}>
                  <code className="mono tabular">
                    {value.display ?? value.handle}
                  </code>
                </td>
                <td style={{ padding: "8px 0" }}>
                  <ProvenanceTag sources={value.sources} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: "grid", gap: 6 }}>
        <span style={{ fontSize: 12, color: "var(--ink-2)" }}>
          Checks against company records
        </span>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {decision.facts.map((fact) => (
            <span
              key={fact.name}
              title={
                fact.decisive
                  ? "This is why the decision went the way it did"
                  : undefined
              }
              style={{
                fontSize: 12,
                padding: "2px 9px",
                borderRadius: 999,
                fontFamily: "var(--font-mono)",
                border: `1px solid ${fact.decisive ? "var(--deny)" : "var(--rule)"}`,
                background: fact.decisive
                  ? "var(--untrusted-soft)"
                  : "var(--surface-2)",
                fontWeight: fact.decisive ? 600 : 400,
              }}
            >
              {fact.name}: {String(fact.value)}
            </span>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        {decision.determiningPolicies.map((id) => {
          const policy = POLICIES.find((p) => p.id === id);
          return (
            <div
              key={id}
              style={{
                borderLeft: `3px solid ${policy && !policy.overridable ? "var(--deny)" : "var(--rule)"}`,
                paddingLeft: 12,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <code className="mono" style={{ fontSize: 12 }}>
                  {id}
                </code>
                {policy && !policy.overridable && (
                  <span
                    style={{
                      fontSize: 11,
                      color: "var(--deny)",
                      fontWeight: 600,
                    }}
                  >
                    NO APPROVAL CAN LIFT THIS
                  </span>
                )}
              </div>
              {policy && (
                <p
                  style={{
                    margin: "2px 0 0",
                    fontSize: 13,
                    color: "var(--ink-2)",
                  }}
                >
                  {policy.explain}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {onShowLineage && (
        <button
          type="button"
          onClick={() => onShowLineage(decision.decisionId)}
          style={{
            justifySelf: "start",
            border: "1px solid var(--rule)",
            borderRadius: "var(--radius-sm)",
            background: "var(--surface-2)",
            color: "var(--ink)",
            padding: "6px 12px",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          Show where these came from
        </button>
      )}
    </TiltCard>
  );
}
