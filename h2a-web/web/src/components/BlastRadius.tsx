/**
 * What a rework of this artifact would put back in question.
 *
 * Shown beside the regenerate control rather than as a tab of its own, because that is
 * the moment the information changes a decision. Regenerating one file is a single click
 * and the classes that depended on its old shape are nowhere near the button.
 *
 * Direct and transitive dependents stay separate — one that calls you directly almost
 * certainly needs re-reviewing, one three hops out usually does not, and a single
 * combined number would be dismissed as noise within a week.
 */

export interface BlastData {
  target: string; found: boolean;
  direct: { target: string; layer: string; via: string[]; rules: number; test_class: string | null }[];
  indirect: { target: string; layer: string; distance: number; rules: number }[];
  schema: string[]; shared_schema: string[];
  tests_to_rerun: string[]; rules_at_risk: number; behaviours_invalidated: number;
  summary: { direct: number; indirect: number; tests: number; shared_objects: number };
}

export default function BlastRadius({ b }: { b: BlastData | null | undefined }) {
  if (!b || !b.found) return null;
  const { summary: s } = b;
  const nothing = !s.direct && !s.indirect && !s.shared_objects;

  if (nothing) {
    return (
      <div className="bl none">
        ✓ Nothing else depends on this — reworking it is self-contained.
      </div>
    );
  }

  return (
    <details className="bl">
      <summary>
        <span className="bl-icon">⚠</span>
        Reworking this touches <b>{s.direct}</b> dependent artifact{s.direct === 1 ? '' : 's'}
        {s.indirect > 0 && <> and <b>{s.indirect}</b> further out</>}
        {s.tests > 0 && <> · <b>{s.tests}</b> test{s.tests === 1 ? '' : 's'} to re-run</>}
      </summary>

      <div className="bl-body">
        {b.direct.length > 0 && (
          <div className="bl-grp">
            <span className="u-lbl">Depends on this directly</span>
            {b.direct.map((d) => (
              <div key={d.target} className="bl-row">
                <code>{d.target}</code>
                <span className="faint">{d.layer}</span>
                {d.rules > 0 && <span className="bl-rules">{d.rules} rule(s)</span>}
                <span className="bl-via mono">via {d.via.join(', ')}</span>
              </div>
            ))}
          </div>
        )}

        {b.indirect.length > 0 && (
          <div className="bl-grp">
            <span className="u-lbl">Further out — usually safe, worth knowing</span>
            {b.indirect.map((d) => (
              <div key={d.target} className="bl-row dim">
                <code>{d.target}</code>
                <span className="faint">{d.distance} hops</span>
              </div>
            ))}
          </div>
        )}

        {b.shared_schema.length > 0 && (
          <div className="bl-grp">
            <span className="u-lbl">Shared objects</span>
            <p className="bl-note">
              Other artifacts write to these too — this is how a rework reaches code that
              never references it directly.
            </p>
            {b.shared_schema.map((o) => <code key={o} className="pv-chip">{o}</code>)}
          </div>
        )}

        {b.behaviours_invalidated > 0 && (
          <div className="bl-grp">
            <span className="u-lbl">Recorded evidence</span>
            <p className="bl-note">
              {b.behaviours_invalidated} replayed behaviour(s) stop being evidence for this
              artifact the moment it is regenerated.
            </p>
          </div>
        )}

        {b.tests_to_rerun.length > 0 && (
          <div className="bl-grp">
            <span className="u-lbl">Re-run after regenerating</span>
            {b.tests_to_rerun.map((t) => <code key={t} className="pv-chip">{t}</code>)}
          </div>
        )}
      </div>
    </details>
  );
}
