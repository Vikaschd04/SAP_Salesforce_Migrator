import type { Artifact, StageStatus } from '../types';
import { STAGES } from '../useRun';

interface Props {
  stages: Record<string, { status: StageStatus; detail?: string }>;
  artifacts: Artifact[];
  status: string;
}

const statusColor = (s: string) =>
  s === 'accepted' ? 'var(--good)' : s === 'error' ? 'var(--danger)'
    : s === 'needs_review' ? 'var(--warn)' : 'var(--accent-2)';

export default function PipelineFlow({ stages, artifacts, status }: Props) {
  const running = status === 'running';
  const built = artifacts.length;

  // Layout: an "Agents" hub on the left fanning out to one node per artifact.
  const rowH = 30;
  const H = Math.max(artifacts.length * rowH + 24, 130);
  const hubX = 74, hubY = H / 2, tX = 250;

  return (
    <div className="tabpanel">
      {/* stage ribbon */}
      <div className="flow-ribbon">
        {STAGES.map((s, i) => {
          const st = stages[s.id]?.status || 'pending';
          return (
            <div key={s.id} className={`flow-stage ${st}`}>
              <span className="fs-dot" />{s.n}
              {i < STAGES.length - 1 && <span className={`fs-conn ${st === 'done' ? 'done' : ''}`} />}
            </div>
          );
        })}
      </div>

      {/* agents → artifacts graph */}
      {artifacts.length === 0 ? (
        <p className="empty">As the Builder + Critic produce each target, it appears here — a live map of the migration, colored by review status.</p>
      ) : (
        <>
          <div className="flow-legend">
            <span><i style={{ background: 'var(--good)' }} /> accepted</span>
            <span><i style={{ background: 'var(--warn)' }} /> needs review</span>
            <span><i style={{ background: 'var(--danger)' }} /> failed</span>
            <span className="dim">{built} artifact{built === 1 ? '' : 's'}</span>
          </div>
          <svg className="flow-graph" viewBox={`0 0 470 ${H}`} width="100%" preserveAspectRatio="xMinYMin meet">
            {/* edges */}
            {artifacts.map((a, i) => {
              const y = 20 + i * rowH + 6;
              return <path key={'e' + a.target_name} d={`M ${hubX} ${hubY} C ${(hubX + tX) / 2} ${hubY}, ${(hubX + tX) / 2} ${y}, ${tX} ${y}`}
                fill="none" stroke={statusColor(a.status)} strokeOpacity={0.5} strokeWidth={1.5}
                className={running ? 'flow-edge live' : 'flow-edge'} />;
            })}
            {/* hub */}
            <circle cx={hubX} cy={hubY} r={26} className={`flow-hub ${running ? 'live' : ''}`} />
            <text x={hubX} y={hubY - 2} textAnchor="middle" className="flow-hub-t">Builder</text>
            <text x={hubX} y={hubY + 11} textAnchor="middle" className="flow-hub-t">+ Critic</text>
            {/* artifact nodes */}
            {artifacts.map((a, i) => {
              const y = 20 + i * rowH + 6;
              return (
                <g key={a.target_name}>
                  <circle cx={tX} cy={y} r={6} fill={statusColor(a.status)} />
                  {a.review_flags?.length ? <circle cx={tX} cy={y} r={9} fill="none" stroke="var(--warn)" strokeWidth={1.2} /> : null}
                  <text x={tX + 14} y={y + 4} className="flow-node-t">
                    {a.target_name}<tspan className="flow-node-tag"> · {a.is_lwc ? 'LWC' : (a.apex_pattern || 'Apex')}</tspan>
                  </text>
                </g>
              );
            })}
          </svg>
        </>
      )}
    </div>
  );
}
