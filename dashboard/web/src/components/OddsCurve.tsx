import { motion } from "framer-motion";
import { appsForConfidence, cumulativeProb, curvePoints } from "../lib/odds";

type Props = { p: number; sent: number; cadence: number; projectionDays?: number };

const W = 560;
const H = 280;
const PAD_L = 44;
const PAD_R = 18;
const PAD_T = 18;
const PAD_B = 34;

export function OddsCurve({ p, sent, cadence, projectionDays = 14 }: Props) {
  const projectedN = Math.round(sent + cadence * projectionDays);
  const xMax = Math.max(appsForConfidence(p, 0.97) || 100, projectedN + 6, sent + 6, 60);

  const xOf = (n: number) => PAD_L + (n / xMax) * (W - PAD_L - PAD_R);
  const yOf = (prob: number) => PAD_T + (1 - prob) * (H - PAD_T - PAD_B);

  const pts = curvePoints(p, xMax, 80);
  const line = pts.map((pt, i) => `${i ? "L" : "M"}${xOf(pt.n).toFixed(1)} ${yOf(pt.prob).toFixed(1)}`).join(" ");
  const area = `${line} L${xOf(xMax).toFixed(1)} ${yOf(0).toFixed(1)} L${xOf(0).toFixed(1)} ${yOf(0).toFixed(1)} Z`;

  const curProb = cumulativeProb(sent, p);
  const projProb = cumulativeProb(projectedN, p);

  return (
    <svg className="curve-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cumulative interview odds as applications stack up">
      <defs>
        <linearGradient id="fillGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--glow-rose)" stopOpacity="0.42" />
          <stop offset="100%" stopColor="var(--glow-rose)" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--glow-gold)" />
          <stop offset="100%" stopColor="var(--glow-rose)" />
        </linearGradient>
      </defs>

      {[0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}>
          <line x1={PAD_L} y1={yOf(g)} x2={W - PAD_R} y2={yOf(g)} stroke="rgba(255,255,255,0.09)" strokeWidth="1" />
          <text x={PAD_L - 9} y={yOf(g) + 3} textAnchor="end" fontSize="10" fill="var(--dusk-ink-soft)">
            {g * 100}%
          </text>
        </g>
      ))}

      <path d={area} fill="url(#fillGrad)" />
      <motion.path
        d={line}
        fill="none"
        stroke="url(#lineGrad)"
        strokeWidth="3"
        strokeLinecap="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 1.1, ease: "easeInOut" }}
      />

      {/* projection: dotted hop from now to two weeks out */}
      {projectedN > sent && (
        <>
          <line
            x1={xOf(sent)}
            y1={yOf(curProb)}
            x2={xOf(projectedN)}
            y2={yOf(projProb)}
            stroke="var(--glow-gold)"
            strokeWidth="1.6"
            strokeDasharray="3 4"
            opacity="0.8"
          />
          <circle cx={xOf(projectedN)} cy={yOf(projProb)} r="5" fill="none" stroke="var(--glow-gold)" strokeWidth="2" />
          <text x={xOf(projectedN)} y={yOf(projProb) - 11} textAnchor="middle" fontSize="10.5" fill="var(--glow-gold)" fontWeight="700">
            +2wk · {Math.round(projProb * 100)}%
          </text>
        </>
      )}

      {/* current position glows (SMIL pulse — avoids framer-motion's SVG r handling) */}
      <circle cx={xOf(sent)} cy={yOf(curProb)} r="6.5" fill="var(--glow-rose)">
        <animate attributeName="r" values="6.5;9;6.5" dur="2.2s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="1;0.7;1" dur="2.2s" repeatCount="indefinite" />
      </circle>
      <text x={xOf(sent)} y={yOf(curProb) + 22} textAnchor="middle" fontSize="11" fill="var(--dusk-ink)" fontWeight="700">
        you · {sent} mature
      </text>

      <text x={W - PAD_R} y={H - 8} textAnchor="end" fontSize="10" fill="var(--dusk-ink-soft)">
        matured applications →
      </text>
    </svg>
  );
}
