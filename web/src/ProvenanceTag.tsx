/* The one component the whole console is built around.
 *
 * Provenance is signalled three ways at once: a texture (hatched or solid), a colour, and
 * the source name in text. Colour alone would fail for colour-blind users and would not
 * survive a screenshot in a slide deck.
 */

export type Provenance =
  | "USER"
  | "COMPANY_DB"
  | "SYSTEM"
  | "EXTERNAL_EMAIL"
  | "EXTERNAL_ATTACHMENT"
  | "WEB"
  | "MODEL_READER";

const TRUSTED_SOURCES: ReadonlySet<Provenance> = new Set<Provenance>([
  "USER",
  "COMPANY_DB",
  "SYSTEM",
]);

const LABELS: Record<Provenance, string> = {
  USER: "USER",
  COMPANY_DB: "VENDOR MASTER",
  SYSTEM: "SYSTEM",
  EXTERNAL_EMAIL: "EXTERNAL EMAIL",
  EXTERNAL_ATTACHMENT: "ATTACHMENT",
  WEB: "WEB",
  MODEL_READER: "READER",
};

export function isTrusted(sources: readonly Provenance[]): boolean {
  // An empty source set is not trusted: unknown provenance reads as untrusted.
  return sources.length > 0 && sources.every((s) => TRUSTED_SOURCES.has(s));
}

export function ProvenanceTag({ sources }: { sources: readonly Provenance[] }) {
  const trusted = isTrusted(sources);
  const text = sources.map((s) => LABELS[s]).join(" + ") || "UNKNOWN";

  return (
    <span
      title={
        trusted ? "From company records" : "Derived from untrusted content"
      }
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 9px",
        borderRadius: 999,
        fontSize: 12,
        letterSpacing: "0.04em",
        fontWeight: 600,
        color: trusted ? "var(--trusted)" : "var(--untrusted)",
        background: trusted ? "var(--trusted-soft)" : "var(--untrusted-soft)",
        backgroundImage: trusted ? "none" : "var(--hatch)",
        border: `1px solid ${trusted ? "var(--trusted)" : "var(--untrusted)"}`,
      }}
    >
      <span aria-hidden="true">{trusted ? "●" : "▨"}</span>
      {text}
    </span>
  );
}
