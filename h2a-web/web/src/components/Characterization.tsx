import { useMemo, useState } from 'react';
import type { Characterization as Char, CharMode, CharRow } from '../types';

/**
 * Golden-master parity: the customer's own JUnit suite replayed against the generated Apex.
 *
 * Every other view in this cockpit asks whether the new code *looks* right. This one asks
 * whether it *behaves* the same, against evidence the customer's team wrote and trusted
 * for years. So the design leads with how far each row can actually be trusted — an
 * undifferentiated green count would be the one dishonest thing we could put here.
 */

const META: Record<CharMode, { label: string; trust: string; blurb: string }> = {
  direct: {
    label: 'Direct', trust: 'Strong',
    blurb: 'The signature survived the migration. The replay calls the same method with the '
         + 'same recorded values — a failure is a real behavioural difference.',
  },
  adapter: {
    label: 'Bridged', trust: 'Medium',
    blurb: 'The migration reshaped this call, so bridging code arranges the inputs. The '
         + 'expected value is still a recorded fact; the plumbing around it is generated.',
  },
  manual: {
    label: 'Manual', trust: 'None',
    blurb: 'Mocks, object graphs or a target that failed to build. These need a human.',
  },
};
const ORDER: CharMode[] = ['direct', 'adapter', 'manual'];

export default function Characterization({ ch }: { ch: Char | null }) {
  const [only, setOnly] = useState<CharMode | 'all'>('all');
  const s = ch?.summary;
  const rows = useMemo(
    () => (ch?.behaviors || []).filter((r) => only === 'all' || r.mode === only),
    [ch, only],
  );

  if (!ch || !s || s.total === 0) {
    return (
      <div className="tabpanel">
        <p className="empty">
          Your existing JUnit tests are a recorded log of how the legacy system actually
          behaved. Those recorded cases get replayed against the generated Apex here.{' '}
          <em>Nothing to show: no JUnit tests were found in this codebase.</em>
        </p>
      </div>
    );
  }

  const runnable = s.runnable ?? (s.direct + (s.bridged || 0));

  return (
    <div className="tabpanel">
      <div className="rule-hero">
        <div className="rule-score">
          <span className="rule-num num">{runnable}<span className="rule-den">/{s.total}</span></span>
          <span className="u-lbl" style={{ margin: 0 }}>recorded behaviours replayed against the Apex</span>
        </div>
        <div className="rule-bar" role="img"
          aria-label={`${s.direct} direct, ${s.bridged || 0} bridged, ${s.manual} manual`}>
          {s.direct ? <span className="rb ch-direct" style={{ flexGrow: s.direct }} title={`${s.direct} direct`} /> : null}
          {s.bridged ? <span className="rb ch-adapter" style={{ flexGrow: s.bridged }} title={`${s.bridged} bridged`} /> : null}
          {s.total - runnable ? <span className="rb ch-manual" style={{ flexGrow: s.total - runnable }}
            title={`${s.total - runnable} not replayable`} /> : null}
        </div>
      </div>

      {ch.classes?.length > 0 && (
        <div className="note-inline good">
          Generated and deployed with the project:{' '}
          {ch.classes.map((c) => <code key={c}>{c}.cls</code>).reduce<React.ReactNode[]>(
            (acc, el, i) => (i ? [...acc, ', ', el] : [el]), [])}
          {' '}— run them in a scratch org for the reproduce/differ verdict.
        </div>
      )}

      <div className="chips-row">
        <button className={`btn-mini ${only === 'all' ? 'sel' : ''}`} onClick={() => setOnly('all')}>
          All {s.total}
        </button>
        {ORDER.map((m) => {
          const n = m === 'adapter' ? (s.bridged || 0) : m === 'manual' ? s.total - runnable : s.direct;
          return !n ? null : (
            <button key={m} className={`btn-mini ch-f ${m} ${only === m ? 'sel' : ''}`}
              onClick={() => setOnly(m)} title={META[m].blurb}>
              {n} {META[m].label.toLowerCase()}
            </button>
          );
        })}
      </div>

      <table className="rule-tbl">
        <thead>
          <tr><th>Evidence</th><th>Recorded behaviour</th><th>Legacy call</th><th>Now</th><th>Note</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => <Row key={r.id} r={r} />)}
        </tbody>
      </table>

      <p className="rule-caveat">
        <strong>Where the values come from.</strong> Every expected value asserted here was
        <em> recorded</em> from the original system — none is inferred. For bridged rows the model
        only arranges the inputs; it is never told the expected value and never writes the
        assertion. That separation is what keeps a bridged test evidence rather than a second opinion.
      </p>
    </div>
  );
}

function Row({ r }: { r: CharRow }) {
  const [open, setOpen] = useState(false);
  const args = (r.args || []).map((a) => a.java).join(', ');
  const expected = r.expects_exception || r.expected?.java || '—';
  return (
    <>
      <tr className={`rule-row ch-${r.mode}`}>
        <td>
          <span className={`chip rule ch-${r.mode}`}>{META[r.mode].label}</span>
          <span className="ch-trust">{META[r.mode].trust}</span>
        </td>
        <td className="rule-txt">
          {r.label}
          <span className="rule-id">{r.id}</span>
        </td>
        <td className="ch-call">
          <code>{r.source_class}.{r.target_method}({args})</code>
          <span className="ch-arrow">→ <code>{expected}</code></span>
        </td>
        <td>{r.target ? <code>{r.target}</code> : <span className="rule-none">nothing</span>}</td>
        <td className="rule-ev">
          {r.reason}
          {r.bridge && (
            <button className="ch-peek" onClick={() => setOpen((v) => !v)}>
              {open ? 'hide bridge' : 'show bridge'}
            </button>
          )}
        </td>
      </tr>
      {open && r.bridge && (
        <tr className="ch-bridge-row">
          <td colSpan={5}>
            <pre className="ch-bridge">{r.bridge.setup}
{`System.assertEquals(${expected}, ${r.bridge.result_expr});   // written from the recorded fact`}</pre>
          </td>
        </tr>
      )}
    </>
  );
}
