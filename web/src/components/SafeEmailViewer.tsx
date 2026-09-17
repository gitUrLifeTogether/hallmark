/* Showing an attacker's message to a person, safely.
 *
 * The backend has already sanitised this HTML. It is still rendered inside a sandboxed
 * frame with no allowances granted, because defence in depth is cheap here: the frame
 * costs nothing and catches anything the sanitiser missed. `srcDoc` with an empty `sandbox`
 * attribute means no scripts, no forms, no navigation, and no same-origin access.
 *
 * The hidden passages are shown *above* the message rather than in place. A reviewer
 * deciding a bank-change review needs to see the concealed instruction first; finding it
 * inline would mean reading the attacker's framing before the evidence.
 */

import { useState } from "react";
import type { RenderedEmail } from "../lib/types";

export function SafeEmailViewer({ email }: { email: RenderedEmail }) {
  const [revealed, setRevealed] = useState(true);

  return (
    <section style={{ display: "grid", gap: 12 }}>
      <header style={{ display: "grid", gap: 4 }}>
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <strong style={{ fontSize: 15 }}>{email.subject}</strong>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              padding: "1px 8px",
              borderRadius: 999,
              color: "var(--untrusted)",
              background: "var(--untrusted-soft)",
              backgroundImage: "var(--hatch)",
              border: "1px solid var(--untrusted)",
            }}
          >
            ▨ EXTERNAL EMAIL
          </span>
        </div>
        <div style={{ color: "var(--ink-2)", fontSize: 13 }}>
          <code className="mono">{email.sender}</code>
          {" · DKIM "}
          <strong
            style={{
              color: email.dkim === "pass" ? "var(--allow)" : "var(--deny)",
            }}
          >
            {email.dkim}
          </strong>
        </div>
      </header>

      {email.hidden.length > 0 && (
        <div
          style={{
            border: "1px solid var(--deny)",
            borderRadius: "var(--radius-md)",
            padding: 14,
            background: "var(--untrusted-soft)",
            backgroundImage: "var(--hatch)",
            display: "grid",
            gap: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <strong style={{ color: "var(--deny)", fontSize: 13 }}>
              {email.hidden.length === 1
                ? "This message has a hidden passage"
                : `This message has ${email.hidden.length} hidden passages`}
            </strong>
            <button
              type="button"
              onClick={() => setRevealed((r) => !r)}
              style={{
                border: "1px solid var(--rule)",
                borderRadius: "var(--radius-sm)",
                background: "var(--surface)",
                color: "var(--ink)",
                padding: "2px 10px",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              {revealed ? "Hide" : "Reveal"}
            </button>
          </div>

          {revealed &&
            email.hidden.map((passage) => (
              <div key={passage.text} style={{ display: "grid", gap: 3 }}>
                <span style={{ fontSize: 11, color: "var(--ink-2)" }}>
                  {passage.technique}
                </span>
                <p
                  style={{
                    margin: 0,
                    fontSize: 14,
                    background: "var(--surface)",
                    padding: "8px 10px",
                    borderRadius: "var(--radius-sm)",
                  }}
                >
                  {passage.text}
                </p>
              </div>
            ))}
        </div>
      )}

      <iframe
        title={`Message ${email.emailId}, rendered without scripts`}
        // Empty sandbox: every capability withheld, including scripts and same-origin.
        sandbox=""
        srcDoc={`<!doctype html><meta charset="utf-8"><style>
          body{font:15px/1.55 system-ui,sans-serif;color:#15191C;margin:14px;background:#fff}
          p{margin:0 0 10px}
        </style>${email.html}`}
        style={{
          width: "100%",
          minHeight: 260,
          border: "1px solid var(--rule)",
          borderRadius: "var(--radius-md)",
          background: "#fff",
        }}
      />
      <p style={{ margin: 0, fontSize: 12, color: "var(--ink-3)" }}>
        Sanitised server-side and shown with scripts disabled. Nothing in this
        message can run.
      </p>
    </section>
  );
}
