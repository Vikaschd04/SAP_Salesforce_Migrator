/**
 * The audit as a deliverable — who approved what, on what evidence.
 *
 * Laid out so the weaker reading is the one a skimmer takes away: an unattended run
 * leads with "unreviewed" in the danger colour, and the "does not certify" column sits
 * beside the evidence rather than below it, at the same weight. A panel that put the
 * green numbers first and the gaps behind a disclosure would be read as assurance.
 */
export interface SignOffData {
  contract_id: string; generated_at: string; recipe: string;
  supervised: boolean; reviewers: string[];
  gates_reviewed_by_a_human: string[]; gates_auto_approved: string[];
  approvals: { gate: string; action: string; actor: string | null;
               supervised: boolean; at: string; note: string }[];
  completeness: Record<string, number>;
  rules: { total?: number; asserted?: number; implemented?: number;
           at_risk?: number; dropped?: number };
  characterization: { total?: number; replayed?: number };
  provenance: { methods?: number; linked?: number; coverage?: number; high?: number };
  org_verified: boolean;
  cost: { total_usd?: number; priced?: boolean };
  requests: number;
  caveats: string[];
}

const GATES: Record<string, string> = {
  discovery: 'Discovery', plan: 'Plan', build: 'Build',
};

const when = (iso: string) => {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '—' : d.toLocaleString();
};

export default function SignOff({ s }: { s: SignOffData | null }) {
  if (!s) {
    return <p className="empty">The sign-off contract is issued when a run finishes — who
      approved which stage, on what evidence, and what it does not certify.</p>;
  }

  return (
    <div className="so">
      <header className={`so-head ${s.supervised ? '' : 'unreviewed'}`}>
        <div>
          <h3>{s.supervised
            ? `${s.gates_reviewed_by_a_human.length} of 3 gates approved by ${s.reviewers.join(', ') || 'an unnamed reviewer'}`
            : 'Unreviewed — no human approved any stage of this run'}</h3>
          <p>{s.org_verified
            ? 'Deploy-verified: a Salesforce org compiled this code.'
            : 'Not deploy-verified — no Salesforce org has compiled this code.'}</p>
        </div>
        <code className="so-id" title="A hash over the facts certified, not this page's wording">
          {s.contract_id}
        </code>
      </header>

      {!s.supervised && (
        <p className="so-warn">This run was unattended. Every gate was approved
          automatically so it could proceed without a person — a convenience, not a
          decision. Nothing here has been reviewed by anyone.</p>
      )}

      <div className="so-cols">
        <section>
          <h4>Approvals</h4>
          {s.approvals.length === 0
            ? <p className="so-none">No review gates were opened.</p>
            : (
              <ul className="so-gates">
                {s.approvals.map((a, i) => (
                  <li key={i} className={a.supervised ? '' : 'auto'}>
                    <b>{GATES[a.gate] || a.gate}</b>
                    <span className="so-by">{a.actor || (a.supervised ? 'unnamed' : 'no reviewer')}</span>
                    <span className="so-at">{when(a.at)}</span>
                    {a.note && <em>{a.note}</em>}
                  </li>
                ))}
              </ul>
            )}

          <h4>Evidence</h4>
          <table className="so-tbl">
            <tbody>
              {!!s.rules.total && (
                <Row label="Rules with a test asserting them"
                  value={`${s.rules.asserted ?? 0}/${s.rules.total}`} />
              )}
              {!!s.characterization.total && (
                <Row label="Recorded behaviours replayed"
                  value={`${s.characterization.replayed ?? 0}/${s.characterization.total}`} />
              )}
              {!!s.provenance.methods && (
                <Row label="Methods traced to origin"
                  value={`${s.provenance.linked ?? 0}/${s.provenance.methods} (${s.provenance.coverage ?? 0}%)`} />
              )}
              <Row label="Deploy-verified" value={s.org_verified ? 'yes' : 'no'}
                bad={!s.org_verified} />
              {s.cost.total_usd !== undefined && (
                <Row label="Spend"
                  value={`$${(s.cost.total_usd || 0).toFixed(2)}${s.cost.priced === false ? '+' : ''} · ${s.requests} calls`} />
              )}
            </tbody>
          </table>
        </section>

        <section>
          <h4>What this does <b>not</b> certify</h4>
          {s.caveats.length === 0
            ? <p className="so-none">Nothing outstanding was recorded — read the evidence
              rather than relying on this line.</p>
            : <ul className="so-caveats">{s.caveats.map((c, i) => (
                <li key={i}>{c.replace(/\*\*/g, '')}</li>))}</ul>}
        </section>
      </div>

      <p className="so-note">
        Proven by evidence, not by assertion. Every figure above is a fact the tool
        observed or a claim with its basis named — and the gaps sit beside them at the
        same weight, because a page that buried them would be worth exactly as much as
        the burying. The full document is <code>SIGN_OFF.md</code> under Reports.
      </p>
    </div>
  );
}

const Row = ({ label, value, bad }: { label: string; value: string; bad?: boolean }) => (
  <tr><td>{label}</td><td className={`num ${bad ? 'bad' : ''}`}>{value}</td></tr>
);
