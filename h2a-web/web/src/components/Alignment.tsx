/**
 * Intent · implementation · proof, on one row.
 *
 * Not a text diff — a diff across two languages compares punctuation. This answers the
 * question a reviewer actually has: this rule existed, where does it live now, and what
 * proves it still holds?
 */
export interface AlignmentData {
  rows: {
    rule: string; source_class: string; target: string | null;
    java_method: string | null; java_lines: number[] | null;
    apex_method: string | null; apex_lines: number[] | null;
    link_confidence: string | null; proof: string | null; proof_kind: string;
    broken_at: string | null;
  }[];
  summary: { rules: number; aligned: number; proven: number; replayed: number; broken: number };
}

const PROOF: Record<string, [string, string]> = {
  replayed: ['✓ replayed', 'good'],
  asserted: ['~ test references it', 'warn'],
  implemented: ['no test evidence', 'dim'],
  at_risk: ['target failed to build', 'bad'],
  dropped: ['nothing carries this rule', 'bad'],
  none: ['—', 'dim'],
};

export default function Alignment({ a }: { a: AlignmentData | null }) {
  if (!a || !a.summary.rules) {
    return <div className="tabpanel"><p className="empty">
      Every business rule traced from intent to implementation to proof appears here.{' '}
      <em>Nothing yet — the mock provider does not infer business rules.</em></p></div>;
  }
  return (
    <div className="tabpanel">
      <div className="rule-hero">
        <div className="rule-score">
          <span className="rule-num num">{a.summary.aligned}<span className="rule-den">/{a.summary.rules}</span></span>
          <span className="u-lbl" style={{ margin: 0 }}>rules traced from intent to implementation</span>
        </div>
        <div className="al-counts">
          <span className="chip rule ch-direct">{a.summary.replayed} replayed</span>
          <span className="chip rule ch-adapter">{a.summary.proven - a.summary.replayed} asserted</span>
          {a.summary.broken > 0 && <span className="chip rule ch-manual">{a.summary.broken} not traced</span>}
        </div>
      </div>

      <table className="rule-tbl al-tbl">
        <thead><tr><th>Intent</th><th>Implementation</th><th>Proof</th></tr></thead>
        <tbody>
          {a.rows.map((r, i) => {
            const [label, tone] = PROOF[r.proof_kind] || PROOF.none;
            return (
              <tr key={i} className={r.apex_method ? '' : 'al-broken'}>
                <td className="rule-txt">
                  {r.rule}
                  <span className="rule-id">
                    {r.source_class}{r.java_method ? `.${r.java_method}` : ''}
                    {r.java_lines ? ` ${r.java_lines[0]}–${r.java_lines[1]}` : ''}
                  </span>
                </td>
                <td>
                  {r.apex_method ? (
                    <>
                      <code>{r.target}.{r.apex_method}</code>
                      <span className="rule-id">
                        lines {r.apex_lines![0]}–{r.apex_lines![1]} · {r.link_confidence} confidence
                      </span>
                    </>
                  ) : <span className="al-gap">{r.broken_at}</span>}
                </td>
                <td className={`al-proof ${tone}`}>
                  {label}
                  {r.proof && r.proof_kind === 'replayed' && <span className="rule-id">{r.proof}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <p className="rule-caveat">
        <strong>The chain names its weakest link.</strong> Rule → class is recorded fact, and
        Apex → Java is provenance graded exact or normalised. Rule → <em>method</em> is keyword
        overlap, because a rule is extracted from a class rather than a line — so a row that
        cannot complete the chain says where it broke instead of guessing the rest.
      </p>
    </div>
  );
}
