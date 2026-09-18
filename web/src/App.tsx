/* The console.
 *
 * Four views, in the order a person actually uses them: what the run did, why one decision
 * went the way it did, the message behind it, and what is waiting on a human.
 *
 * Live run and Approvals talk to the deployed API; the rest render a recorded run. In
 * both cases the console reports decisions and provenance and never re-derives them,
 * because a second implementation of the rules would eventually disagree with the one
 * that matters.
 */

import { useEffect, useState } from "react";
import { DecisionCard } from "./components/DecisionCard";
import { Approvals } from "./features/Approvals";
import { LiveRun } from "./features/LiveRun";
import { Bench } from "./features/Bench";
import { SplitReplay } from "./features/SplitReplay";
import { LineageGraph } from "./components/LineageGraph";
import { SafeEmailViewer } from "./components/SafeEmailViewer";
import {
  ATTACK_EMAIL,
  DECISIONS,
  LINEAGE_EDGES,
  LINEAGE_NODES,
  POLICIES,
  RUN_SUMMARY,
} from "./lib/demoData";
import { useLiveRun } from "./lib/liveStore";
import { formatPaise } from "./lib/types";

type View =
  | "live"
  | "run"
  | "replay"
  | "bench"
  | "lineage"
  | "evidence"
  | "approvals"
  | "policies";

const TABS: { id: View; label: string }[] = [
  { id: "live", label: "Live run" },
  { id: "run", label: "Run" },
  { id: "replay", label: "Split replay" },
  { id: "bench", label: "Bench" },
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

// Derived from the tabs rather than listed again. Keeping a second copy is how a view
// ends up reachable from the navigation but not from its own URL, which is a bug that
// looks like the page silently ignoring the link.
const VIEW_IDS = new Set<string>(TABS.map((tab) => tab.id));

/** The view named in the URL, so a screen can be linked to and reloaded onto. */
function viewFromHash(): View {
  const candidate = window.location.hash.replace(/^#/, "");
  return (VIEW_IDS.has(candidate) ? candidate : "run") as View;
}

/** Says which run a screen is describing.
 *
 * Silence here would be worse than showing the wrong run: a viewer could not tell a
 * submitted email from the recorded example, and the console's whole subject is knowing
 * where something came from.
 */
function RunSource({ live, planner }: { live: boolean; planner?: string }) {
  return (
    <p style={{ margin: 0, fontSize: 13, color: "var(--ink-2)" }}>
      {live
        ? `Showing the run you just submitted${planner ? ` — ${planner}` : ""}.`
        : "Showing the recorded acceptance run. Submit an email on Live run to replace it."}
    </p>
  );
}

export default function App() {
  const [view, setViewState] = useState<View>(viewFromHash);

  // A submitted run replaces the recorded one everywhere, so every screen describes the
  // same thing. Falling back keeps the console useful before anything has been submitted.
  const live = useLiveRun();
  const decisions = live?.decisions ?? DECISIONS;
  const lineageNodes = live?.lineage.nodes ?? LINEAGE_NODES;
  const lineageEdges = live?.lineage.edges ?? LINEAGE_EDGES;
  const email = live?.email ?? ATTACK_EMAIL;
  const summary = live
    ? {
        executed: live.counts.executed,
        pendingApproval: live.counts.pendingApproval,
        denied: live.counts.denied,
        paidPaise: RUN_SUMMARY.paidPaise,
        blockedPaise: RUN_SUMMARY.blockedPaise,
      }
    : RUN_SUMMARY;

  const setView = (next: View) => {
    setViewState(next);
    window.location.hash = next;
  };

  useEffect(() => {
    const onHashChange = () => setViewState(viewFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

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

      {view === "live" && <LiveRun />}

      {view === "run" && (
        <section style={{ display: "grid", gap: 20 }}>
          <RunSource live={live !== null} planner={live?.plannerLabel} />
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
              value={String(summary.executed)}
              tone="var(--allow)"
            />
            <Stat
              label="waiting on a person"
              value={String(summary.pendingApproval)}
              tone="var(--pending)"
            />
            <Stat
              label="refused"
              value={String(summary.denied)}
              tone="var(--deny)"
            />
            <Stat label="total paid" value={formatPaise(summary.paidPaise)} />
            <Stat
              label="blocked value"
              value={formatPaise(summary.blockedPaise)}
              tone="var(--deny)"
            />
          </div>

          {decisions.map((decision) => (
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

      {view === "replay" && <SplitReplay />}

      {view === "bench" && <Bench />}

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
            {live
              ? "Where this run's values came from"
              : "Why the payment to Suryodaya was refused"}
          </h2>
          <RunSource live={live !== null} planner={live?.plannerLabel} />
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
            nodes={lineageNodes}
            edges={lineageEdges}
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
          <div style={{ marginBottom: 12 }}>
            <RunSource live={live !== null} planner={live?.plannerLabel} />
          </div>
          <SafeEmailViewer email={email} />
        </section>
      )}

      {view === "approvals" && <Approvals />}

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
