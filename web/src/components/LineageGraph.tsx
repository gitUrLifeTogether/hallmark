/* The chain of custody behind one decision, drawn left to right.
 *
 * Hand-drawn SVG rather than a graph library: these graphs are small and their layout is
 * known (sources, then derived values, then the decision), and the provenance styling —
 * hatched for untrusted, solid for trusted — has to be exact, which is easier to guarantee
 * when the marks are ours.
 *
 * A selection edge is drawn differently from a derivation on purpose. A vendor record is
 * the company's own data and is trusted, but untrusted content chose *which* record to
 * load, and that influence is part of the story even though it does not taint the value.
 */

import type { LineageEdge, LineageNode } from "../lib/types";
import { isTrusted } from "../lib/types";

const COLUMN_WIDTH = 260;
const ROW_HEIGHT = 92;
const NODE_WIDTH = 210;
const NODE_HEIGHT = 58;
const PADDING = 24;

interface Props {
  nodes: LineageNode[];
  edges: LineageEdge[];
  /** Highlights the path back from this node to its roots. */
  focus?: string;
}

interface Placed extends LineageNode {
  x: number;
  y: number;
}

function place(nodes: LineageNode[]): Placed[] {
  const byDepth = new Map<number, LineageNode[]>();
  for (const node of nodes) {
    byDepth.set(node.depth, [...(byDepth.get(node.depth) ?? []), node]);
  }

  return nodes.map((node) => {
    const column = byDepth.get(node.depth) ?? [];
    const row = column.indexOf(node);
    return {
      ...node,
      x: PADDING + node.depth * COLUMN_WIDTH,
      y: PADDING + row * ROW_HEIGHT,
    };
  });
}

/** Every node the focus node ultimately derives from, so the path can be highlighted. */
function ancestorsOf(handle: string, edges: LineageEdge[]): Set<string> {
  const seen = new Set<string>([handle]);
  const queue = [handle];

  while (queue.length > 0) {
    const current = queue.pop() as string;
    for (const edge of edges) {
      if (edge.to === current && !seen.has(edge.from)) {
        seen.add(edge.from);
        queue.push(edge.from);
      }
    }
  }
  return seen;
}

export function LineageGraph({ nodes, edges, focus }: Props) {
  const placed = place(nodes);
  const byHandle = new Map(placed.map((n) => [n.handle, n]));
  const onPath = focus ? ancestorsOf(focus, edges) : null;

  const depths = nodes.map((n) => n.depth);
  const width = PADDING * 2 + (Math.max(...depths) + 1) * COLUMN_WIDTH;
  const rows = new Map<number, number>();
  for (const d of depths) rows.set(d, (rows.get(d) ?? 0) + 1);
  const height = PADDING * 2 + Math.max(...rows.values()) * ROW_HEIGHT;

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Where each argument to this decision came from"
      style={{ maxWidth: "100%", fontFamily: "var(--font-ui)" }}
    >
      <defs>
        {/* The texture that marks untrusted provenance, matching the tags elsewhere. */}
        <pattern
          id="hatch"
          patternUnits="userSpaceOnUse"
          width="7"
          height="7"
          patternTransform="rotate(135)"
        >
          <rect width="7" height="7" fill="var(--untrusted-soft)" />
          <line
            x1="0"
            y1="0"
            x2="0"
            y2="7"
            stroke="var(--untrusted)"
            strokeWidth="2"
            opacity="0.35"
          />
        </pattern>
        <marker
          id="arrow"
          markerWidth="9"
          markerHeight="9"
          refX="8"
          refY="3"
          orient="auto"
        >
          <path d="M0,0 L0,6 L8,3 z" fill="var(--ink-3)" />
        </marker>
      </defs>

      {edges.map((edge) => {
        const from = byHandle.get(edge.from);
        const to = byHandle.get(edge.to);
        if (!from || !to) return null;

        const highlighted = onPath
          ? onPath.has(edge.from) && onPath.has(edge.to)
          : true;
        const x1 = from.x + NODE_WIDTH;
        const y1 = from.y + NODE_HEIGHT / 2;
        const x2 = to.x;
        const y2 = to.y + NODE_HEIGHT / 2;
        const midX = (x1 + x2) / 2;

        return (
          <g
            key={`${edge.from}-${edge.to}-${edge.kind}`}
            opacity={highlighted ? 1 : 0.25}
          >
            <path
              d={`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`}
              fill="none"
              stroke="var(--ink-3)"
              strokeWidth={edge.kind === "arg" ? 2 : 1.5}
              // A selection edge is influence, not derivation, so it is drawn dashed.
              strokeDasharray={edge.kind === "selection" ? "5 4" : undefined}
              markerEnd="url(#arrow)"
            />
            <text
              x={midX}
              y={(y1 + y2) / 2 - 6}
              textAnchor="middle"
              fontSize="11"
              fill="var(--ink-3)"
            >
              {edge.label}
            </text>
          </g>
        );
      })}

      {placed.map((node) => {
        const trusted = isTrusted(node.sources);
        const highlighted = onPath ? onPath.has(node.handle) : true;
        const isDecision = node.kind === "decision";

        return (
          <g key={node.handle} opacity={highlighted ? 1 : 0.3}>
            <rect
              x={node.x}
              y={node.y}
              width={NODE_WIDTH}
              height={NODE_HEIGHT}
              rx={10}
              fill={trusted ? "var(--trusted-soft)" : "url(#hatch)"}
              stroke={
                isDecision
                  ? "var(--deny)"
                  : trusted
                    ? "var(--trusted)"
                    : "var(--untrusted)"
              }
              strokeWidth={isDecision ? 2 : 1.5}
            />
            <text
              x={node.x + 14}
              y={node.y + 24}
              fontSize="13"
              fontWeight={600}
              fill="var(--ink)"
            >
              {node.label.length > 26
                ? `${node.label.slice(0, 25)}…`
                : node.label}
            </text>
            <text
              x={node.x + 14}
              y={node.y + 42}
              fontSize="11"
              fill="var(--ink-2)"
            >
              {trusted ? "● " : "▨ "}
              {node.sources.join(" + ")}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
