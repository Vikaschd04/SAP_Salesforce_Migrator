import { useState } from 'react';

/**
 * Which artifacts actually need a person.
 *
 * The band leads, never the score — there is no ground truth for "how risky is this
 * class", so the number is a sorting device and the reasons are the product. Every row
 * carries the reasons that produced its rank.
 */
export interface TriageData {
  items: {
    target: string; layer: string; score: number; band: 'must' | 'review' | 'routine';
    reasons: string[]; rules: number; complexity: string; sources: string[];
    hazards: { critical: number; high: number; medium: number };
    critic: { errors: number; warnings: number };
  }[];
  summary: { total: number; must: number; review: number; routine: number; needs_you: number };
}

const BANDS = {
  must: ['Must review', 'Broken, hazardous, or carrying a decision only a human can make.'],
  review: ['Worth a look', 'Elevated risk, but nothing blocking.'],
  routine: ['Routine', 'Built clean, no business rules, mechanical layer — safe to bulk-approve.'],
} as const;

export default function Triage({ t }: { t: TriageData | null }) {
  const [only, setOnly] = useState<string>('all');
  if (!t || !t.summary.total) {
    return <div className="tabpanel"><p className="empty">
      Ranking appears once artifacts have been built — it turns "review 400 classes" into
      "these 12 need you".</p></div>;
  }
  const rows = t.items.filter((i) => only === 'all' || i.band === only);

  return (
    <div className="tabpanel">
      <div className="tr-head">
        <div>
          <b>{t.summary.needs_you} of {t.summary.total} need your attention</b>
          <p>{t.summary.routine} routine — safe to approve in bulk.</p>
        </div>
        <div className="chips-row" style={{ marginBottom: 0 }}>
          <button className={`btn-mini ${only === 'all' ? 'sel' : ''}`}
            onClick={() => setOnly('all')}>All {t.summary.total}</button>
          {(['must', 'review', 'routine'] as const).map((b) => t.summary[b] ? (
            <button key={b} className={`btn-mini tr-f ${b} ${only === b ? 'sel' : ''}`}
              onClick={() => setOnly(b)} title={BANDS[b][1]}>
              {t.summary[b]} {BANDS[b][0].toLowerCase()}
            </button>
          ) : null)}
        </div>
      </div>

      <div className="tr-list">
        {rows.map((i) => (
          <div key={i.target} className={`tr-item ${i.band}`}>
            <div className="tr-top">
              <span className={`chip tr-band ${i.band}`}>{BANDS[i.band][0]}</span>
              <b>{i.target}</b>
              <span className="faint">{i.layer}</span>
              {i.rules > 0 && <span className="tr-meta">{i.rules} rule(s)</span>}
              {i.complexity !== '—' && <span className="tr-meta">{i.complexity} complexity</span>}
            </div>
            <ul className="tr-why">{i.reasons.map((r, k) => <li key={k}>{r}</li>)}</ul>
            <div className="tr-src mono">from {i.sources.join(', ')}</div>
          </div>
        ))}
      </div>

      <p className="rule-caveat">
        <strong>The rank is a sorting device, not a measurement.</strong> There is no ground
        truth for how risky a class is, so every row lists the reasons behind its placement
        and the band is what to act on. If you disagree with one, the reasons tell you why it
        landed there.
      </p>
    </div>
  );
}
