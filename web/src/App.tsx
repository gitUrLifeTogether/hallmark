/* Console placeholder.
 *
 * Deliberately small: it exists so the toolchain and the design tokens are proven, and so
 * the screens built later start from a working page rather than an empty directory. The
 * data below is hard-coded from the deterministic acceptance run.
 */

import { ProvenanceTag, type Provenance } from "./ProvenanceTag";

type Row = {
  label: string;
  value: string;
  sources: Provenance[];
  verdict: "EXECUTED" | "BLOCKED";
  note: string;
};

const ROWS: Row[] = [
  {
    label: "Suryodaya Metals · INV-SM-2288",
    value: "₹1,57,500.00",
    sources: ["COMPANY_DB"],
    verdict: "EXECUTED",
    note: "Paid to the account on file.",
  },
  {
    label: "Suryodaya Metals · INV-SM-2291",
    value: "XXXXXXXX1234",
    sources: ["EXTERNAL_EMAIL", "MODEL_READER"],
    verdict: "BLOCKED",
    note: "The destination account came from an external email and is not the account on file.",
  },
];

function Verdict({ verdict }: { verdict: Row["verdict"] }) {
  const blocked = verdict === "BLOCKED";
  return (
    <span
      style={{
        fontFamily: "var(--font-display)",
        fontSize: 17,
        letterSpacing: "0.06em",
        padding: "2px 12px",
        display: "inline-block",
        transform: "rotate(-2deg)",
        color: blocked ? "var(--deny)" : "var(--allow)",
        border: `2px solid ${blocked ? "var(--deny)" : "var(--allow)"}`,
        borderRadius: "var(--radius-sm)",
      }}
    >
      {verdict}
    </span>
  );
}

export default function App() {
  return (
    <main
      style={{
        maxWidth: 860,
        margin: "0 auto",
        padding: "48px 16px",
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
        <p style={{ margin: 0, color: "var(--ink-2)", maxWidth: 620 }}>
          Every value an agent handles carries a record of where it came from.
          Before a payment executes, a policy checks not only what the agent is
          doing, but where each argument came from.
        </p>
      </header>

      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--rule)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-1)",
          overflow: "hidden",
        }}
      >
        {ROWS.map((row, index) => (
          <article
            key={row.label}
            style={{
              padding: 20,
              display: "grid",
              gap: 10,
              borderTop: index === 0 ? "none" : "1px solid var(--rule)",
            }}
          >
            <div
              style={{
                display: "flex",
                gap: 12,
                alignItems: "center",
                flexWrap: "wrap",
                justifyContent: "space-between",
              }}
            >
              <strong>{row.label}</strong>
              <Verdict verdict={row.verdict} />
            </div>
            <div
              style={{
                display: "flex",
                gap: 10,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <code className="tabular">{row.value}</code>
              <ProvenanceTag sources={row.sources} />
            </div>
            <p style={{ margin: 0, color: "var(--ink-2)", fontSize: 14 }}>
              {row.note}
            </p>
          </article>
        ))}
      </section>

      <footer style={{ color: "var(--ink-3)", fontSize: 13 }}>
        Placeholder. Runs, lineage, approvals and the attack bench land here
        next.
      </footer>
    </main>
  );
}
