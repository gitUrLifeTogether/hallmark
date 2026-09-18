/* The most recent live run, shared by every view.
 *
 * Run, Lineage and Evidence used to read one hardcoded module, so they could only ever
 * show a run that existed when the bundle was built. Submitting an email changed one tab
 * and left the rest describing something else entirely, which is a poor thing for a
 * console whose subject is provenance.
 *
 * This holds what the backend recorded for the latest run and nothing more. It does not
 * compute outcomes: a console that re-derived a verdict would eventually disagree with the
 * system it is meant to be reporting on.
 */

import { useEffect, useState } from "react";
import type {
  Decision,
  LineageEdge,
  LineageNode,
  RenderedEmail,
} from "./types";

export interface RunDetail {
  runId: string;
  decisions: Decision[];
  lineage: { nodes: LineageNode[]; edges: LineageEdge[] };
  email: RenderedEmail;
  counts: {
    executed: number;
    pendingApproval: number;
    denied: number;
    paid: number;
  };
  /** Which planner produced it, in the run's own words. */
  plannerLabel?: string;
}

const KEY = "hallmark.lastRun";

let current: RunDetail | null = restore();
const listeners = new Set<(detail: RunDetail | null) => void>();

function restore(): RunDetail | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as RunDetail) : null;
  } catch {
    // A blocked or full store must not stop the console rendering.
    return null;
  }
}

/** Publish the latest run. Passing null returns every view to the recorded run. */
export function setLiveRun(detail: RunDetail | null): void {
  current = detail;
  try {
    if (detail) sessionStorage.setItem(KEY, JSON.stringify(detail));
    else sessionStorage.removeItem(KEY);
  } catch {
    // Persistence is a convenience; the in-memory value is what views read.
  }
  for (const listener of listeners) listener(current);
}

/** Subscribe to the latest run. Returns null while none has been submitted. */
export function useLiveRun(): RunDetail | null {
  const [detail, setDetail] = useState<RunDetail | null>(current);

  useEffect(() => {
    listeners.add(setDetail);
    setDetail(current);
    return () => {
      listeners.delete(setDetail);
    };
  }, []);

  return detail;
}
