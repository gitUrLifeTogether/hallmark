/* The API client.
 *
 * Requests go through a relative `/api` path that the dev server proxies to the deployed
 * stack. That keeps the deployment's address out of the bundle and avoids cross-origin
 * preflight entirely in development.
 *
 * The token is held in memory only. Putting it in localStorage would leave it readable by
 * anything that ever manages to run script on this origin, and the console renders
 * attacker-controlled email, which is precisely the wrong place to keep a bearer token
 * somewhere persistent.
 */

import type { PendingApproval } from "./types";

const BASE = "/api";

let token: string | null = null;
let role: string | null = null;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const text = await response.text();
  const parsed: unknown = text ? JSON.parse(text) : {};

  if (!response.ok) {
    const error = (parsed as { error?: { code?: string; message?: string } })
      .error;
    throw new ApiError(
      response.status,
      error?.code ?? "UNKNOWN",
      error?.message ?? `request failed with ${response.status}`,
    );
  }

  return parsed as T;
}

export async function login(userId: string): Promise<{ role: string }> {
  const result = await request<{ token: string; role: string }>(
    "POST",
    "/auth/login",
    {
      userId,
    },
  );
  token = result.token;
  role = result.role;
  return { role: result.role };
}

export function currentRole(): string | null {
  return role;
}

export function isSignedIn(): boolean {
  return token !== null;
}

export function signOut(): void {
  token = null;
  role = null;
}

export async function health(): Promise<{ status: string; stage: string }> {
  return request("GET", "/health");
}

export async function listApprovals(): Promise<PendingApproval[]> {
  const result = await request<{ approvals: PendingApproval[] }>(
    "GET",
    "/approvals",
  );
  return result.approvals;
}

export interface DecisionResult {
  approvalId: string;
  status: string;
  executed: boolean;
  reasonCode?: string;
  determiningPolicies?: string[];
}

export async function decideApproval(
  approvalId: string,
  decision: "APPROVE" | "REJECT",
): Promise<DecisionResult> {
  return request("POST", `/approvals/${approvalId}/decision`, { decision });
}

export interface RunSubmission {
  sender: string;
  subject: string;
  body: string;
  attachmentText?: string;
}

export interface RunAccepted {
  runId: string;
  status: string;
}

export interface RunStatus {
  runId: string;
  status: string;
  summary: {
    verdict?: string;
    reasonCode?: string;
    policies?: string[];
    paid?: number;
    error?: string;
  } | null;
}

/** Submit an email for a live run. Returns as soon as it is queued, never when it is done. */
export async function submitRun(
  submission: RunSubmission,
): Promise<RunAccepted> {
  return request("POST", "/runs", submission);
}

/** Status for a run, for a browser that reconnected and missed the events. */
export async function getRun(runId: string): Promise<RunStatus> {
  return request("GET", `/runs/${runId}`);
}
