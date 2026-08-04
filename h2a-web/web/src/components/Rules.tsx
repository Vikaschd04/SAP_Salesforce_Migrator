import { useMemo, useState } from 'react';
import type { RuleLedger, RuleStatus } from '../types';

/**
 * The business-rule ledger: completeness measured in rules rather than files.
 *
 * "100% of classes converted" is the metric that is easy to hit and answers the wrong
 * question. This view answers the one people actually ask — *does it still do what it
 * did* — by tracing every rule the Comprehender found through to the code, and putting
 * the rules nothing carries at the top where they cannot be missed.
 */

const META: Record<RuleStatus, { label: string; blurb: string }> = {
  dropped: { label: 'Dropped', blurb: 'No generated artifact carries this rule — migrate it by hand.' },
  at_risk: { label: 'At risk', blurb: 'Its target failed to generate, so the rule did not survive.' },
  implemented: { label: 'Implemented', blurb: 'Present in the generated code, but no test evidence for it.' },
  asserted: { label: 'Asserted', blurb: 'Implemented, and the generated test references what it describes.' },
};
const ORDER: RuleStatus[] = ['dropped', 'at_risk', 'implemented', 'asserted'];

export default function Rules({ led }: { led: RuleLedger | null }) {
  const [only, setOnly] = useState<RuleStatus | 'all'>('all');
  const s = led?.summary;
  const rows = useMemo(
    () => (led?.rules || []).filter((r) => only === 'all' || r.status === only),
    [led, only],
  );

  if (!led || !s || s.total === 0) {
    return (
      <div className="tabpanel">
        <p className="empty">
          Every business rule found in the source is traced here — to the Apex that implements
          it and the test that asserts it. Rules that no generated artifact carries are listed
          first. <em>The mock provider does not infer rules; run with a real provider to populate this.</em>
        </p>
      </div>
    );
  }

  const risky = s.dropped + s.at_risk;

  return (
    <div className="tabpanel">
      <div className="rule-hero">
        <div className="rule-score">
          <span className="rule-num num">{s.asserted}<span className="rule-den">/{s.total}</span></span>
          <span className="u-lbl" style={{ margin: 0 }}>business rules preserved and asserted</span>
        </div>
        <div className="rule-bar" role="img"
          aria-label={`${s.asserted} asserted, ${s.implemented} implemented, ${s.at_risk} at risk, ${s.dropped} dropped`}>
          {ORDER.slice().reverse().map((k) => {
            const n = s[k as keyof typeof s] as number;
            return n ? <span key={k} className={`rb ${k}`} style={{ flexGrow: n }} title={`${n} ${META[k].label}`} /> : null;
          })}
        </div>
      </div>

      {risky > 0 && (
        <div className="rule-warn">
          <strong>{risky} rule{risky === 1 ? '' : 's'} did not make it into working code.</strong>{' '}
          These are the highest-risk items in the migration — review them before go-live.
        </div>
      )}

      <div className="chips-row">
        <button className={`btn-mini ${only === 'all' ? 'sel' : ''}`} onClick={() => setOnly('all')}>
          All {s.total}
        </button>
        {ORDER.map((k) => {
          const n = s[k as keyof typeof s] as number;
          return !n ? null : (
            <button key={k} className={`btn-mini rule-f ${k} ${only === k ? 'sel' : ''}`}
              onClick={() => setOnly(k)} title={META[k].blurb}>
              {n} {META[k].label.toLowerCase()}
            </button>
          );
        })}
      </div>

      <table className="rule-tbl">
        <thead>
          <tr><th>Status</th><th>Business rule</th><th>From</th><th>Implemented in</th><th>Evidence</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={`rule-row ${r.status}`}>
              <td><span className={`chip rule ${r.status}`}>{META[r.status].label}</span></td>
              <td className="rule-txt">{r.rule}<span className="rule-id">{r.id}</span></td>
              <td><code>{r.source}</code></td>
              <td>{r.target === '—' ? <span className="rule-none">nothing</span> : <code>{r.target}</code>}</td>
              <td className="rule-ev">{r.evidence}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="rule-caveat">
        <strong>How “asserted” is decided:</strong> the generated test’s text overlaps the rule’s
        distinctive terms. That is real evidence, but it is a heuristic — read it as “a test
        plausibly covers this”, not as proof of behavioural equivalence. Use a deploy-verified
        run and your own regression suite for proof.
      </p>
    </div>
  );
}
