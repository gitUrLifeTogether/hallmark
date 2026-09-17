/* The approval queue, against the live API.
 *
 * Two things here are deliberate rather than cosmetic.
 *
 * A refusal is shown as an outcome, not an error. An approver being told their role is
 * insufficient has learned something true and useful; styling it like a crash would teach
 * them to retry or to find someone who will click it for them.
 *
 * And the result of approving is reported exactly as the server gave it. Approving re-runs
 * the checks, so it can legitimately come back approved-but-not-executed. Showing that as a
 * success would be a lie, and it is the case that matters most.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  currentRole,
  decideApproval,
  listApprovals,
  login,
} from "../lib/api";
import type { PendingApproval } from "../lib/types";
import { formatPaise } from "../lib/types";

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready" };

interface Outcome {
  approvalId: string;
  tone: "good" | "refused" | "bad";
  message: string;
}

const DEMO_USERS = [
  { id: "ananya", label: "Ananya · AP lead" },
  { id: "vikram", label: "Vikram · Controller" },
];

export function Approvals() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [role, setRole] = useState<string | null>(currentRole());
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);

  const refresh = useCallback(async () => {
    setStatus({ kind: "loading" });
    try {
      setApprovals(await listApprovals());
      setStatus({ kind: "ready" });
    } catch (error) {
      setStatus({
        kind: "error",
        message:
          error instanceof ApiError
            ? `${error.code}: ${error.message}`
            : "the API is unreachable — is the stack deployed?",
      });
    }
  }, []);

  useEffect(() => {
    if (role) void refresh();
  }, [role, refresh]);

  const signIn = async (userId: string) => {
    setStatus({ kind: "loading" });
    try {
      const result = await login(userId);
      setRole(result.role);
    } catch {
      setStatus({
        kind: "error",
        message: "could not sign in — is the stack deployed?",
      });
    }
  };

  const decide = async (
    approval: PendingApproval,
    decision: "APPROVE" | "REJECT",
  ) => {
    try {
      const result = await decideApproval(approval.approvalId, decision);
      setOutcomes((previous) => [
        {
          approvalId: approval.approvalId,
          tone: result.executed ? "good" : "refused",
          message: result.executed
            ? `${result.status} and executed`
            : `${result.status}, but the re-check did not permit execution` +
              (result.reasonCode ? ` (${result.reasonCode})` : ""),
        },
        ...previous,
      ]);
      await refresh();
    } catch (error) {
      const conflict = error instanceof ApiError && error.status === 409;
      setOutcomes((previous) => [
        {
          approvalId: approval.approvalId,
          // A conflict is a correct refusal, not a fault. Say so plainly.
          tone: conflict ? "refused" : "bad",
          message:
            error instanceof ApiError
              ? conflict
                ? `Refused: ${error.message}`
                : `${error.code}: ${error.message}`
              : "the request failed",
        },
        ...previous,
      ]);
      await refresh();
    }
  };

  if (!role) {
    return (
      <section style={{ display: "grid", gap: 12, maxWidth: 460 }}>
        <p style={{ margin: 0, color: "var(--ink-2)", fontSize: 14 }}>
          Sign in as a demo user. The role decides which amounts you can
          approve, and it comes from the token rather than anything this page
          sends.
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {DEMO_USERS.map((user) => (
            <button
              key={user.id}
              type="button"
              onClick={() => void signIn(user.id)}
              style={{
                padding: "8px 14px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--trusted)",
                background: "var(--trusted-soft)",
                color: "var(--trusted)",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {user.label}
            </button>
          ))}
        </div>
        {status.kind === "error" && (
          <p style={{ margin: 0, color: "var(--deny)", fontSize: 13 }}>
            {status.message}
          </p>
        )}
      </section>
    );
  }

  return (
    <section style={{ display: "grid", gap: 14 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <span style={{ fontSize: 13, color: "var(--ink-2)" }}>
          Signed in as <strong>{role}</strong>
        </span>
        <button
          type="button"
          onClick={() => void refresh()}
          style={{
            border: "1px solid var(--rule)",
            borderRadius: "var(--radius-sm)",
            background: "var(--surface)",
            color: "var(--ink)",
            padding: "4px 12px",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          Refresh
        </button>
      </div>

      {status.kind === "error" && (
        <p style={{ margin: 0, color: "var(--deny)", fontSize: 13 }}>
          {status.message}
        </p>
      )}

      {outcomes.map((outcome, index) => (
        <p
          key={`${outcome.approvalId}-${index}`}
          style={{
            margin: 0,
            fontSize: 13,
            padding: "8px 12px",
            borderRadius: "var(--radius-sm)",
            border: `1px solid ${outcome.tone === "good" ? "var(--allow)" : outcome.tone === "refused" ? "var(--pending)" : "var(--deny)"}`,
            color:
              outcome.tone === "good"
                ? "var(--allow)"
                : outcome.tone === "refused"
                  ? "var(--pending)"
                  : "var(--deny)",
          }}
        >
          {outcome.message}
        </p>
      ))}

      {status.kind === "ready" && approvals.length === 0 && (
        <p style={{ margin: 0, color: "var(--ink-3)", fontSize: 14 }}>
          Nothing is waiting. Escalations appear here when a payment needs a
          person.
        </p>
      )}

      {approvals.map((approval) => {
        const canApprove =
          role === approval.requiredRole || role === "CONTROLLER";
        return (
          <article
            key={approval.approvalId}
            style={{
              background: "var(--surface)",
              border: "1px solid var(--rule)",
              borderRadius: "var(--radius-lg)",
              padding: 18,
              display: "grid",
              gap: 10,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 10,
                flexWrap: "wrap",
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
            <code
              className="mono"
              style={{ fontSize: 12, color: "var(--ink-3)" }}
            >
              {approval.approvalId} · {approval.tool}
            </code>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={() => void decide(approval, "APPROVE")}
                style={{
                  padding: "6px 14px",
                  borderRadius: "var(--radius-sm)",
                  border: `1px solid ${canApprove ? "var(--allow)" : "var(--rule)"}`,
                  background: canApprove
                    ? "var(--surface)"
                    : "var(--surface-2)",
                  color: canApprove ? "var(--allow)" : "var(--ink-3)",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Approve
              </button>
              <button
                type="button"
                onClick={() => void decide(approval, "REJECT")}
                style={{
                  padding: "6px 14px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--rule)",
                  background: "var(--surface)",
                  color: "var(--ink-2)",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Reject
              </button>
              {!canApprove && (
                <span
                  style={{
                    fontSize: 12,
                    color: "var(--ink-3)",
                    alignSelf: "center",
                  }}
                >
                  Your role is below this amount; the server will refuse it.
                </span>
              )}
            </div>
          </article>
        );
      })}
    </section>
  );
}
