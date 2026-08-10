/**
 * What this run is estimated to cost, shown at the Discovery gate — the last moment
 * before the first billable token. Leads with the range, never a single figure: a point
 * estimate would be wrong in a way that looks authoritative.
 */
export interface ForecastData {
  provider: string; free: boolean; classes: number; targets: number; reused: number;
  calls: number; tokens_in: number;
  cost: { low: number; high: number; unpriced: string[] };
  minutes: { low: number; high: number };
  review_hours: { low: number; high: number };
  stages: { stage: string; model: string; calls: number; tokens_in: number;
            usd_low: number | null; usd_high: number | null }[];
  assumptions: string[];
}

const usd = (v: number) => (v === 0 ? '$0' : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`);

export default function Forecast({ f }: { f: ForecastData | null }) {
  if (!f) return null;
  return (
    <section className="fc">
      <div className="fc-row">
        <Metric label="Estimated cost"
          value={f.free ? 'Free' : `${usd(f.cost.low)}–${usd(f.cost.high)}`}
          sub={f.free ? 'mock provider' : `${f.calls} model calls`} />
        <Metric label="Runtime" value={`${f.minutes.low}–${f.minutes.high} min`}
          sub="wall clock, at this concurrency" />
        <Metric label="Review effort" value={`${f.review_hours.low}–${f.review_hours.high} h`}
          sub="one reviewer, no rework" />
        {f.reused > 0 && (
          <Metric label="Reused" value={`${f.reused}`} sub="unchanged, not re-billed" good />
        )}
      </div>

      {f.stages.length > 0 && !f.free && (
        <details className="fc-more">
          <summary>Per stage, and what it assumes</summary>
          <table className="fc-tbl">
            <thead><tr><th>Stage</th><th>Model</th><th>Calls</th><th>Input</th><th>Cost</th></tr></thead>
            <tbody>
              {f.stages.map((s) => (
                <tr key={s.stage}>
                  <td>{s.stage}</td>
                  <td><code>{s.model}</code></td>
                  <td className="num">{s.calls}</td>
                  <td className="num">{s.tokens_in.toLocaleString()}</td>
                  <td className="num">{s.usd_low === null ? 'unpriced'
                    : `${usd(s.usd_low)}–${usd(s.usd_high!)}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="fc-assume">{f.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        </details>
      )}

      <p className="fc-note">
        A range, deliberately — output length varies with how much the model decides to say,
        and a single figure would be wrong in a way that looks authoritative.
      </p>
    </section>
  );
}

const Metric = ({ label, value, sub, good }: {
  label: string; value: string; sub: string; good?: boolean;
}) => (
  <div className={`fc-metric ${good ? 'good' : ''}`}>
    <span className="u-lbl">{label}</span>
    <b className="num">{value}</b>
    <span className="fc-sub">{sub}</span>
  </div>
);
