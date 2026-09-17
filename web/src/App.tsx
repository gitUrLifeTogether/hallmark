/* The console.
 *
 * Four views, in the order a person actually uses them: what the run did, why one decision
 * went the way it did, the message behind it, and what is waiting on a human.
 *
 * Everything shown here comes from a recorded run. The console renders decisions and
 * provenance; it never re-derives them, because a second implementation of the rules would
 * eventually disagree with the one that matters.
 */

import { useState } from "react";
import { DecisionCard } from "./components/DecisionCard";
import { LineageGraph } from "./components/LineageGraph";
import { SafeEmailViewer } from "./components/SafeEmailViewer";
import {
  APPROVALS,
  ATTACK_EMAIL,
  DECISIONS,
  LINEAGE_EDGES,
  LINEAGE_NODES,
  POLICIES,
  RUN_SUMMARY,
} from "./lib/demoData";
import { formatPaise } from "./lib/types";

type View = "run" | "lineage" | "evidence" | "approvals" | "policies";

const TABS: { id: View; label: string }[] = [
  { id: "run", label: "Run" },
  { id: "lineage", label: "Lineage" },
  { id: "evidence", label: "Evidence" },
  { id: "approvals", label: "Approvals" },
  { id: "policies", label: "Policies" },
];

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div style={{ display: "grid", gap: 2 }}>
      <span
        className="tabular"
        style={{ fontSize: 28, color: tone ?? "var(--ink)" }}
      >
        {value}
      </span>
      <span style={{ fontSize: 12, color: "var(--ink-2)" }}>{label}</span>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("run");
  const [focus, setFocus] = useState<string | undefined>("dec_000094");

  return (
    <main
      style={{
        maxWidth: 1040,
        margin: "0 auto",
        padding: "40px 16px",
        display: "grid",
        gap: 24,
      }}
    >
      <header style={{ display: "grid", gap: 8 }}>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 40,
            margin: 0,
            fontWeight: 400,
          }}
        >
          Hallmark Console
        </h1>
        <p style={{ margin: 0, color: "var(--ink-2)", maxWidth: 660 }}>
          Every value an agent handles carries a record of where it came from.
          Before a payment executes, a policy checks not only what the agent is
          doing, but where each argument came from.
        </p>
      </header>

      <nav
        style={{ display: "flex", gap: 6, flexWrap: "wrap" }}
        aria-label="Console sections"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setView(tab.id)}
            aria-current={view === tab.id ? "page" : undefined}
            style={{
              padding: "6px 14px",
              borderRadius: 999,
              fontSize: 14,
              cursor: "pointer",
              border: `1px solid ${view === tab.id ? "var(--trusted)" : "var(--rule)"}`,
              background:
                view === tab.id ? "var(--trusted-soft)" : "var(--surface)",
              color: view === tab.id ? "var(--trusted)" : "var(--ink-2)",
              fontWeight: view === tab.id ? 600 : 400,
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {view === "run" && (
        <section style={{ display: "grid", gap: 20 }}>
          <div
            style={{
              display: "flex",
              gap: 36,
              flexWrap: "wrap",
              background: "var(--surface)",
              border: "1px solid var(--rule)",
              borderRadius: "var(--radius-lg)",
              padding: 20,
            }}
          >
            <Stat
              label="paid automatically"
              value={String(RUN_SUMMARY.executed)}
              tone="var(--allow)"
            />
            <Stat
              label="waiting on a person"
              value={String(RUN_SUMMARY.pendingApproval)}
              tone="var(--pending)"
            />
            <Stat
              label="refused"
              value={String(RUN_SUMMARY.denied)}
              tone="var(--deny)"
            />
            <Stat
              label="total paid"
              value={formatPaise(RUN_SUMMARY.paidPaise)}
            />
            <Stat
              label="blocked value"
              value={formatPaise(RUN_SUMMARY.blockedPaise)}
              tone="var(--deny)"
            />
          </div>

          {DECISIONS.map((decision) => (
            <DecisionCard
              key={decision.decisionId}
              decision={decision}
              onShowLineage={(id) => {
                setFocus(id);
                setView("lineage");
              }}
            />
          ))}
        </section>
      )}

      {view === "lineage" && (
        <section
          style={{
            background: "var(--surface)",
            border: "1px solid var(--rule)",
            borderRadius: "var(--radius-lg)",
            padding: 20,
            display: "grid",
            gap: 12,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 21, fontWeight: 600 }}>
            Why the payment to Suryodaya was refused
          </h2>
          <p
            style={{
              margin: 0,
              color: "var(--ink-2)",
              fontSize: 14,
              maxWidth: 680,
            }}
          >
            The destination account traces back to the body of email 19. It was
            never in the vendor master, so no policy permits paying it — and no
            approval can lift that. The dashed edge is influence rather than
            derivation: the vendor record is the company's own, but untrusted
            content chose which record to load.
          </p>
          <LineageGraph
            nodes={LINEAGE_NODES}
            edges={LINEAGE_EDGES}
            focus={focus}
          />
        </section>
      )}

      {view === "evidence" && (
        <section
          style={{
            background: "var(--surface)",
            border: "1px solid var(--rule)",
            borderRadius: "var(--radius-lg)",
            padding: 20,
          }}
        >
          <SafeEmailViewer email={ATTACK_EMAIL} />
        </section>
      )}

      {view === "approvals" && (
        <section style={{ display: "grid", gap: 12 }}>
          {APPROVALS.map((approval) => (
            <article
              key={approval.approvalId}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--rule)",
                borderRadius: "var(--radius-lg)",
                padding: 20,
                display: "grid",
                gap: 10,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: 10,
                }}
              >
                <strong className="tabular" style={{ fontSize: 21 }}>
                  {formatPaise(approval.amountPaise)}
                </strong>
                <span
                  style={{
                    fontSize: 12,
                    color: "var(--pending)",
                    fontWeight: 600,
                  }}
                >
                  {approval.requiredRole} REQUIRED
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 14, color: "var(--ink-2)" }}>
                Above the auto-approve limit. The destination is the account on
                file, so a person can approve this one.
              </p>
              <code
                className="mono"
                style={{ fontSize: 12, color: "var(--ink-3)" }}
              >
                {approval.approvalId}
              </code>
            </article>
          ))}
          <p style={{ margin: 0, fontSize: 13, color: "var(--ink-3)" }}>
            Approving re-runs the checks with a person attached. It does not
            execute anything directly, so a refusal nobody can lift stays
            refused.
          </p>
        </section>
      )}

      {view === "policies" && (
        <section style={{ display: "grid", gap: 12 }}>
          {POLICIES.map((policy) => (
            <article
              key={policy.id}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--rule)",
                borderLeft: `3px solid ${policy.overridable ? "var(--pending)" : "var(--deny)"}`,
                borderRadius: "var(--radius-lg)",
                padding: 16,
                display: "grid",
                gap: 4,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <strong style={{ fontSize: 15 }}>{policy.label}</strong>
                <code
                  className="mono"
                  style={{ fontSize: 12, color: "var(--ink-3)" }}
                >
                  {policy.id}
                </code>
              </div>
              <p style={{ margin: 0, fontSize: 14, color: "var(--ink-2)" }}>
                {policy.explain}
              </p>
              <span
                style={{
                  fontSize: 12,
                  color: policy.overridable ? "var(--pending)" : "var(--deny)",
                  fontWeight: 600,
                }}
              >
                {policy.overridable
                  ? "A person can approve this"
                  : "No approval can lift this"}
              </span>
            </article>
          ))}
          <p style={{ margin: 0, fontSize: 13, color: "var(--ink-3)" }}>
            There is deliberately no action for changing a vendor's bank
            details. Nothing permits it, so no agent can attempt it.
          </p>
        </section>
      )}
    </main>
  );
}
