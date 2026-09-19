/* The product, drawn.
 *
 * An invoice on the desk with a wax seal struck across it — the hallmark the whole project
 * is named for. The document is solid because it is the company's own record; the sheet
 * behind it is hatched, because that is the email it arrived in and anything in that is an
 * attacker's to write. Someone who has read a provenance tag anywhere else in the console
 * already knows how to read this picture, which is the only reason to draw it at all.
 *
 * Drawn rather than photographed, in the palette's own tokens, so it changes with the
 * theme and cannot drift from the rest of the interface the way an exported asset would.
 */

interface Props {
  /** Rendered width in pixels; the drawing scales to it. */
  width?: number;
  /** Decorative next to a heading that already says this, or the label itself. */
  title?: string;
}

export function SealedInvoice({ width = 260, title }: Props) {
  return (
    <svg
      viewBox="0 0 260 200"
      width={width}
      height={(width * 200) / 260}
      role={title ? "img" : "presentation"}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      style={{ maxWidth: "100%", flexShrink: 0 }}
    >
      <defs>
        {/* The same hatch, the same angle, the same weight as every untrusted thing. */}
        <pattern
          id="seal-hatch"
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

        {/* Wax catches light on one side. Two stops, no more: a gradient that draws
         * attention to itself stops being a seal and becomes a button. */}
        <radialGradient id="seal-wax" cx="38%" cy="32%" r="72%">
          <stop offset="0%" stopColor="var(--accent-gold)" stopOpacity="0.95" />
          <stop
            offset="100%"
            stopColor="var(--accent-gold)"
            stopOpacity="0.72"
          />
        </radialGradient>
      </defs>

      {/* The envelope the invoice arrived in: hatched, because an attacker writes it. */}
      <g transform="rotate(-7 96 104)">
        <rect
          x="26"
          y="46"
          width="140"
          height="108"
          rx="6"
          fill="url(#seal-hatch)"
          stroke="var(--untrusted)"
          strokeWidth="1.5"
        />
        <path
          d="M26 52 L96 104 L166 52"
          fill="none"
          stroke="var(--untrusted)"
          strokeWidth="1.5"
          opacity="0.75"
        />
      </g>

      {/* The invoice itself, on the company's own paper. */}
      <g transform="rotate(4 150 108)">
        <rect
          x="84"
          y="34"
          width="132"
          height="142"
          rx="7"
          fill="var(--surface)"
          stroke="var(--rule)"
          strokeWidth="1.5"
        />

        {/* Ruled lines, the same ledger the Runs screen sits on. */}
        {[62, 78, 94, 110, 126].map((y, index) => (
          <line
            key={y}
            x1="100"
            y1={y}
            x2={index % 2 === 0 ? 198 : 176}
            y2={y}
            stroke="var(--rule)"
            strokeWidth="3"
            strokeLinecap="round"
          />
        ))}

        {/* The one figure that matters, weighted like money everywhere else. */}
        <text
          x="100"
          y="158"
          fontSize="15"
          fontWeight="600"
          fill="var(--ink)"
          fontFamily="var(--font-mono)"
        >
          ₹4,62,000
        </text>
      </g>

      {/* The hallmark: struck across both, because the decision covers the whole thing. */}
      <g transform="translate(186 132)">
        <circle r="30" fill="url(#seal-wax)" />
        <circle
          r="30"
          fill="none"
          stroke="var(--accent-gold)"
          strokeWidth="1.5"
          opacity="0.9"
        />
        <circle
          r="23"
          fill="none"
          stroke="var(--surface)"
          strokeWidth="1.2"
          opacity="0.55"
        />
        {/* A struck mark, not a tick: this says "stamped", not "approved". */}
        <path
          d="M-9 2 L-2 9 L10 -8"
          fill="none"
          stroke="var(--surface)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}
