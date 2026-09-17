/* Shapes the console renders. These mirror the API's responses.
 *
 * Provenance is part of every value the console shows, never an afterthought: a component
 * that can render a value without its sources would eventually be used to do exactly that.
 */

export type Provenance =
  | "USER"
  | "COMPANY_DB"
  | "SYSTEM"
  | "EXTERNAL_EMAIL"
  | "EXTERNAL_ATTACHMENT"
  | "WEB"
  | "MODEL_READER";

export type Outcome = "EXECUTED" | "PENDING_APPROVAL" | "DENIED";

export interface LabeledValue {
  handle: string;
  /** Present only for values that passed a type validator. Never free text. */
  display?: string;
  sources: Provenance[];
  trusted: boolean;
}

export interface Fact {
  name: string;
  value: boolean | string | number;
  /** Whether this fact is the reason the decision went the way it did. */
  decisive?: boolean;
}

export interface Decision {
  decisionId: string;
  emailId: string;
  tool: string;
  outcome: Outcome;
  reasonCode: string;
  determiningPolicies: string[];
  args: Record<string, LabeledValue>;
  facts: Fact[];
  at: string;
}

export interface LineageNode {
  handle: string;
  label: string;
  kind: "source" | "value" | "decision";
  sources: Provenance[];
  /** Column in the left-to-right layout. */
  depth: number;
}

export interface LineageEdge {
  from: string;
  to: string;
  kind: "derive" | "selection" | "arg";
  label: string;
}

export interface HiddenPassage {
  technique: string;
  text: string;
}

export interface RenderedEmail {
  emailId: string;
  subject: string;
  sender: string;
  dkim: "pass" | "fail";
  /** Already sanitised by the backend. Rendered in a sandboxed frame regardless. */
  html: string;
  hidden: HiddenPassage[];
}

export interface PendingApproval {
  approvalId: string;
  runId: string;
  tool: string;
  amountPaise: number;
  requiredRole: string;
  status: string;
}

export interface PolicySummary {
  id: string;
  label: string;
  explain: string;
  /** Whether a human approver can lift this refusal. */
  overridable: boolean;
}

export function formatPaise(paise: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
  }).format(paise / 100);
}

export function isTrusted(sources: readonly Provenance[]): boolean {
  const trustedSources = new Set<Provenance>(["USER", "COMPANY_DB", "SYSTEM"]);
  // An empty source set is not trusted: unknown provenance reads as untrusted.
  return sources.length > 0 && sources.every((s) => trustedSources.has(s));
}
