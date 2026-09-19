/* The six mechanisms, then how they chain together.
 *
 * The copy is the plain-language framing the project already uses, not new marketing
 * written for a card: tags that stick, a planner that never reads the text, values that
 * may be shown but never trusted. If a card said something the rest of the system did not
 * do, the card would be the thing that was wrong.
 *
 * Each card flips on hover for a pointer and on tap for a touch screen. Both are wired,
 * because a demonstration that only works with a mouse is one a judge on a phone cannot
 * read at all.
 */

import { useCallback, useEffect, useState } from "react";
import { LifecycleDiagram } from "../components/LifecycleDiagram";

interface Mechanism {
  id: string;
  name: string;
  hook: string;
  /** Two or three sentences, in the terms the rest of the console uses. */
  detail: string;
  icon: JSX.Element;
}

/* Drawn here rather than pulled from an icon set: a tag, a ticket, a split, a window, a
 * stamp and a chain all refer to something the product actually does, and they share the
 * stroke weight of the lineage graph. */
const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const MECHANISMS: Mechanism[] = [
  {
    id: "labels",
    name: "Provenance labels",
    hook: "Every value knows where it came from",
    detail:
      "Every piece of data gets a tag saying where it came from — the user, the company database, an external email, an attachment. Tags stick: if you copy, extract or combine data, the result carries all the tags of everything it came from. There is no function anywhere that removes one.",
    icon: (
      <svg viewBox="0 0 24 24" width="26" height="26" {...stroke}>
        <path d="M3 12l8-8h9v9l-8 8z" />
        <circle cx="16.5" cy="7.5" r="1.4" />
      </svg>
    ),
  },
  {
    id: "handles",
    name: "Handles",
    hook: "The planner names values it cannot read",
    detail:
      "The planner refers to data by opaque claim tickets — h_000123 — rather than by content. It can pass a handle to a tool, but it never receives the text behind one. Untrusted content therefore never enters the context of the thing that holds the tools.",
    icon: (
      <svg viewBox="0 0 24 24" width="26" height="26" {...stroke}>
        <rect x="3" y="7" width="18" height="10" rx="2" />
        <path d="M8 7v10M12 11h5" />
      </svg>
    ),
  },
  {
    id: "split",
    name: "Planner / reader split",
    hook: "Whoever reads the text holds no tools",
    detail:
      "The agent is split in two. A planner decides what to do but never reads untrusted text. A reader reads untrusted text but has no tools and can only fill in a strict form. Assume the reader is fully manipulable — the design still holds, because everything it produces is labelled and bounded.",
    icon: (
      <svg viewBox="0 0 24 24" width="26" height="26" {...stroke}>
        <circle cx="7" cy="9" r="3" />
        <circle cx="17" cy="9" r="3" />
        <path d="M4 20c0-2.2 1.6-4 3-4M17 16c1.4 0 3 1.8 3 4M12 5v14" />
      </svg>
    ),
  },
  {
    id: "declassify",
    name: "Declassification by type",
    hook: "A number cannot carry an instruction",
    detail:
      "A value may be shown to the planner only if it passes a strict validator: amounts, dates, format-checked identifiers. Prose, email addresses and documents never are. So the planner can reason about money and deadlines without ever reading attacker-controlled text — and visibility is never trust.",
    icon: (
      <svg viewBox="0 0 24 24" width="26" height="26" {...stroke}>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M7 9h6M7 13h10M7 17h4" />
      </svg>
    ),
  },
  {
    id: "pep",
    name: "Enforcement point + Cedar",
    hook: "The policy asks where each argument came from",
    detail:
      "Before any consequential action, a guard resolves every argument, computes the facts from company records in code, and asks Cedar whether this action with arguments of this provenance is permitted. A denial is asked again with human approval attached — which is how an escalation is told apart from a refusal nobody can lift.",
    icon: (
      <svg viewBox="0 0 24 24" width="26" height="26" {...stroke}>
        <path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    ),
  },
  {
    id: "lineage",
    name: "Lineage + escalation",
    hook: "Why it was blocked is a query, not an argument",
    detail:
      "Every value and every decision is a node in a graph, so any outcome can be traced back to its roots: this payment was blocked because the account number came from an email, extracted by the reader, and one policy forbids exactly that. Approvable denials go to a person with the evidence attached.",
    icon: (
      <svg viewBox="0 0 24 24" width="26" height="26" {...stroke}>
        <circle cx="5" cy="6" r="2" />
        <circle cx="5" cy="18" r="2" />
        <circle cx="19" cy="12" r="2" />
        <path d="M7 6.8L17 11M7 17.2L17 13" />
      </svg>
    ),
  },
];

function FlipCard({ mechanism }: { mechanism: Mechanism }) {
  const [flipped, setFlipped] = useState(false);

  return (
    <div
      className="hm-flip"
      data-flipped={flipped}
      onMouseEnter={() => setFlipped(true)}
      onMouseLeave={() => setFlipped(false)}
      onClick={() => setFlipped((f) => !f)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          setFlipped((f) => !f);
        }
      }}
      onFocus={() => setFlipped(true)}
      onBlur={() => setFlipped(false)}
      role="button"
      tabIndex={0}
      aria-label={`${mechanism.name}. ${mechanism.detail}`}
      style={{ height: 210, cursor: "pointer" }}
    >
      <div className="hm-flip-inner" style={{ height: "100%" }}>
        <div
          className="hm-face hm-face-front"
          style={{
            height: "100%",
            display: "grid",
            alignContent: "start",
            gap: 10,
            padding: 20,
            background: "var(--surface)",
            border: "1px solid var(--rule)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-2)",
          }}
        >
          <span style={{ color: "var(--trusted)" }}>{mechanism.icon}</span>
          <strong style={{ fontSize: 17, fontWeight: 600 }}>
            {mechanism.name}
          </strong>
          <span style={{ color: "var(--ink-2)", fontSize: 14 }}>
            {mechanism.hook}
          </span>
          <span
            style={{ marginTop: "auto", fontSize: 12, color: "var(--ink-3)" }}
          >
            Hover or tap to read more
          </span>
        </div>

        <div
          className="hm-face hm-face-back"
          style={{
            display: "grid",
            alignContent: "center",
            padding: 20,
            background: "var(--surface-2)",
            border: "1px solid var(--trusted)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-3)",
            fontSize: 14,
            lineHeight: 1.5,
          }}
        >
          {mechanism.detail}
        </div>
      </div>
    </div>
  );
}

export function HowItWorks() {
  // Touch devices have no hover, so the cards must respond to a tap. The click handler
  // above covers that; this only stops a stray double-fire on hybrid devices.
  const [, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);

  const stop = useCallback(
    (event: React.MouseEvent) => event.stopPropagation(),
    [],
  );

  return (
    <section
      className="hm-paper"
      style={{ display: "grid", gap: 28 }}
      onClick={stop}
    >
      <div style={{ display: "grid", gap: 8 }}>
        <h2
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: 28,
            fontWeight: 400,
          }}
        >
          How Hallmark works
        </h2>
        <p style={{ margin: 0, color: "var(--ink-2)", maxWidth: "68ch" }}>
          An agent's instructions and the data it reads arrive through the same
          channel, so anything it reads can try to steer it. Six mechanisms make
          that harmless — none of them by asking a model to make a security
          decision.
        </p>
      </div>

      <div
        style={{
          display: "grid",
          gap: 16,
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
        }}
      >
        {MECHANISMS.map((mechanism) => (
          <FlipCard key={mechanism.id} mechanism={mechanism} />
        ))}
      </div>

      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--rule)",
          borderRadius: "var(--radius-lg)",
          padding: 20,
          boxShadow: "var(--shadow-1)",
        }}
      >
        <LifecycleDiagram />
      </div>
    </section>
  );
}
