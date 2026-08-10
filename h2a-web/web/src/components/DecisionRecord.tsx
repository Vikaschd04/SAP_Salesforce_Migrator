import { useState } from 'react';

/**
 * Every model call in the run, keyed and replayable.
 *
 * The cache was built as a cost optimisation; unchanged, it is an audit trail. Replaying
 * a key returns the identical response, which a re-run cannot promise.
 */
export interface ReplayData {
  recipe: string;
  calls: { seq: number; stage: string; model: string; cache_key: string;
           cached: boolean; prompt_chars: number }[];
  stages: { stage: string; calls: number; cached: number; models: string[]; chars: number }[];
  summary: { total: number; cached: number; live: number; models: string[]; replayable: number };
}

export default function DecisionRecord({ r }: { r: ReplayData | null }) {
  const [all, setAll] = useState(false);
  if (!r || !r.summary.total) {
    return <div className="tabpanel"><p className="empty">
      Every model call is recorded with the hash that reproduces it exactly.{' '}
      <em>No calls yet.</em></p></div>;
  }
  const shown = all ? r.calls : r.calls.slice(0, 25);

  return (
    <div className="tabpanel">
      <div className="rule-hero">
        <div className="rule-score">
          <span className="rule-num num">{r.summary.replayable}</span>
          <span className="u-lbl" style={{ margin: 0 }}>model calls recorded and replayable</span>
        </div>
        <div className="al-counts">
          <span className="chip rule ch-direct">{r.summary.cached} from cache</span>
          <span className="chip rule ch-adapter">{r.summary.live} live</span>
        </div>
      </div>

      <table className="rule-tbl">
        <thead><tr><th>Stage</th><th>Calls</th><th>Cached</th><th>Models</th></tr></thead>
        <tbody>
          {r.stages.map((s) => (
            <tr key={s.stage}>
              <td>{s.stage}</td>
              <td className="num">{s.calls}</td>
              <td className="num">{s.cached}</td>
              <td>{s.models.map((m) => <code key={m}>{m}</code>)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="dr-head">
        <span className="u-lbl" style={{ margin: 0 }}>Calls, in order</span>
        {r.calls.length > 25 && (
          <button className="btn-mini" onClick={() => setAll((v) => !v)}>
            {all ? 'Show first 25' : `Show all ${r.calls.length}`}
          </button>
        )}
      </div>
      <div className="dr-list">
        {shown.map((c) => (
          <div key={c.seq} className="dr-row">
            <span className="dr-seq num">{c.seq}</span>
            <span className="dr-stage">{c.stage}</span>
            <code className="dr-key" title={c.cache_key}>{c.cache_key.slice(0, 16)}…</code>
            <span className={`chip dr-src ${c.cached ? 'cache' : 'live'}`}>
              {c.cached ? 'cache' : 'provider'}
            </span>
          </div>
        ))}
      </div>

      <p className="rule-caveat">
        <strong>The prompts are not stored here, deliberately.</strong> They contain your
        source code, and copying it into a second place on disk would be a liability rather
        than a feature. The hash identifies the call and the response cache already holds
        the answer — together those reproduce any decision exactly, without a second copy
        of anyone's IP.
      </p>
    </div>
  );
}
