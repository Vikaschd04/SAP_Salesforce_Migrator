import { useMemo, useState } from 'react';
import Preflight from './Preflight';

export interface DiscoveryData {
  summary: { files_scanned: number; classes: number; components: number; objects: number; domains: number; total_loc: number };
  tree: { path: string; bytes: number }[];
  classes: {
    name: string; layer: string; file: string; domain: string; loc: number; method_count: number;
    methods: { name: string; returns: string; params: string[] }[];
    fields: string[]; refs: string[];
  }[];
  layers: Record<string, number>;
  domains: Record<string, string[]>;
  edges: { from: string; to: string }[];
  schedule: string[];
  schema: {
    object: string; code: string; field_count: number;
    fields: { name: string; type: string }[]; required: string[]; picklists: Record<string, string[]>;
  }[];
  skipped: { class_name?: string; layer?: string; reason?: string }[];
}

type View = 'overview' | 'files' | 'classes' | 'model';

const LAYER_COLOR: Record<string, string> = {
  Controller: 'var(--blue)', Facade: 'var(--violet)', Service: 'var(--teal)',
  DAO: 'var(--warn)', Model: 'var(--text-faint)', Component: 'var(--violet)', Job: 'var(--good)',
};
const layerColor = (l: string) => LAYER_COLOR[l] || 'var(--text-dim)';

export default function Discovery({ d }: { d: DiscoveryData }) {
  const [view, setView] = useState<View>('overview');
  const [openCls, setOpenCls] = useState<Set<string>>(new Set());
  const [openObj, setOpenObj] = useState<Set<string>>(new Set());
  const [q, setQ] = useState('');

  const toggle = (set: Set<string>, k: string, fn: (s: Set<string>) => void) => {
    const n = new Set(set); n.has(k) ? n.delete(k) : n.add(k); fn(n);
  };

  const s = d.summary || ({} as DiscoveryData['summary']);
  const pf = (d as any).preflight;
  const totalLayer = Object.values(d.layers || {}).reduce((a, b) => a + b, 0) || 1;

  const classes = useMemo(() => {
    const t = q.trim().toLowerCase();
    return !t ? d.classes : d.classes.filter((c) =>
      c.name.toLowerCase().includes(t) || c.layer.toLowerCase().includes(t) || c.domain.toLowerCase().includes(t));
  }, [d.classes, q]);

  const VIEWS: [View, string][] = [
    ['overview', 'Architecture'], ['files', `Files (${(d.tree || []).length})`],
    ['classes', `Classes (${(d.classes || []).length})`], ['model', `Data model (${(d.schema || []).length})`],
  ];

  return (
    <div className="disc">
      {/* What we established before spending anything — the reviewer's first question
          is "did it even understand what I gave it", so it is answered first. */}
      {pf && <Preflight r={pf} compact />}
      <div className="stat-row">
        <Stat n={s.files_scanned} l="files scanned" />
        <Stat n={s.classes} l="backend classes" />
        <Stat n={s.components} l="UI components" />
        <Stat n={s.objects} l="data objects" />
        <Stat n={s.domains} l="domains" />
        <Stat n={s.total_loc} l="lines of code" />
      </div>

      <div className="disc-tabs">
        {VIEWS.map(([id, label]) => (
          <button key={id} className={`btn-mini ${view === id ? 'sel' : ''}`} onClick={() => setView(id)}>{label}</button>
        ))}
      </div>

      {view === 'overview' && (
        <>
          <div className="u-sec">
            <span className="u-lbl">Architecture layers detected</span>
            <div className="layerbar">
              {Object.entries(d.layers || {}).sort((a, b) => b[1] - a[1]).map(([l, n]) => (
                <div key={l} className="layerseg" style={{ flexGrow: n, background: layerColor(l) }} title={`${l}: ${n}`} />
              ))}
            </div>
            <div className="layerkey">
              {Object.entries(d.layers || {}).sort((a, b) => b[1] - a[1]).map(([l, n]) => (
                <span key={l}><i style={{ background: layerColor(l) }} />{l} <b>{n}</b></span>
              ))}
            </div>
          </div>

          <div className="u-sec">
            <span className="u-lbl">Feature domains &amp; how they depend on each other</span>
            <DomainGraph domains={d.domains || {}} edges={d.edges || []} />
          </div>

          {!!(d.schedule || []).length && (
            <div className="u-sec">
              <span className="u-lbl">Migration order (dependency-safe)</span>
              <div className="chips-row">
                {d.schedule.map((x, i) => <span key={x} className="chip">{i + 1}. {x}</span>)}
              </div>
            </div>
          )}

          {!!(d.skipped || []).length && (
            <div className="u-sec">
              <span className="u-lbl">Files with no business logic (will be skipped, with reasons)</span>
              <ul className="u-risks" style={{ paddingLeft: 18, fontSize: 12.5, margin: 0 }}>
                {d.skipped.map((k, i) => <li key={i} style={{ color: 'var(--text-dim)' }}>
                  <code>{k.class_name}</code> — {k.reason}</li>)}
              </ul>
            </div>
          )}
        </>
      )}

      {view === 'files' && <FileTree files={d.tree || []} />}

      {view === 'classes' && (
        <>
          <input className="inp" placeholder="Filter by class, layer or domain…" value={q}
            onChange={(e) => setQ(e.target.value)} style={{ width: '100%', marginBottom: 10 }} />
          {classes.map((c) => {
            const open = openCls.has(c.name);
            return (
              <div className="a-card" key={c.name}>
                <div className="a-head" onClick={() => toggle(openCls, c.name, setOpenCls)}>
                  <span className="tw">{open ? '▾' : '▸'}</span>
                  <span className="a-name">{c.name}</span>
                  <span className="badge" style={{ background: 'transparent', border: `1px solid ${layerColor(c.layer)}`, color: layerColor(c.layer) }}>{c.layer}</span>
                  {c.domain && <span className="badge b-skip">{c.domain}</span>}
                  <span className="a-count num">{c.method_count} methods · {c.loc} LOC</span>
                </div>
                {open && (
                  <div className="a-body">
                    <div className="a-sec"><span className="u-lbl">Source file</span><code>{c.file}</code></div>
                    {!!c.methods.length && (
                      <div className="a-sec"><span className="u-lbl">Methods (what this class does)</span>
                        <ul className="sig-list">
                          {c.methods.map((m, i) => (
                            <li key={i}><span className="sig-ret">{m.returns}</span> <b>{m.name}</b>({m.params.join(', ')})</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {!!c.fields.length && <div className="a-sec"><span className="u-lbl">Fields</span> {c.fields.map((f, i) => <code key={i}>{f}</code>)}</div>}
                    {!!c.refs.length && <div className="a-sec"><span className="u-lbl">Depends on</span> {c.refs.map((r, i) => <code key={i}>{r}</code>)}</div>}
                  </div>
                )}
              </div>
            );
          })}
        </>
      )}

      {view === 'model' && (
        <>
          {(d.schema || []).length === 0 && <p className="empty">No items.xml data model found in this codebase.</p>}
          {(d.schema || []).map((o) => {
            const open = openObj.has(o.object);
            return (
              <div className="a-card" key={o.object}>
                <div className="a-head" onClick={() => toggle(openObj, o.object, setOpenObj)}>
                  <span className="tw">{open ? '▾' : '▸'}</span>
                  <span className="a-name">{o.object}</span>
                  {o.code && <span className="badge b-skip">from {o.code}</span>}
                  <span className="a-count num">{o.field_count} fields</span>
                </div>
                {open && (
                  <div className="a-body">
                    <table><thead><tr><th>Field</th><th>Type</th><th>Required</th></tr></thead>
                      <tbody>{o.fields.map((f) => (
                        <tr key={f.name}>
                          <td><code>{f.name}</code></td><td className="dim">{f.type}</td>
                          <td>{o.required.includes(f.name) ? <span className="badge b-flag">required</span> : ''}</td>
                        </tr>))}
                      </tbody></table>
                    {Object.keys(o.picklists || {}).length > 0 && (
                      <div className="a-sec"><span className="u-lbl">Picklist values</span>
                        {Object.entries(o.picklists).map(([k, v]) => (
                          <div key={k} style={{ fontSize: 12, marginTop: 3 }}><code>{k}</code> → {v.join(', ')}</div>))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}

function Stat({ n, l }: { n?: number; l: string }) {
  return <div className="stat"><div className="stat-n num">{(n ?? 0).toLocaleString()}</div><div className="stat-l">{l}</div></div>;
}

/** Domains on a ring with dependency edges — how the system is wired, at a glance.
 *
 * Labels sit *radially outside* the ring rather than stacked above each node. Domain
 * names come from real class names (`OrderFulfilment`, `PricingBreakdownPopulator`) and
 * are long; centring them all above their node made neighbours overlap into mush as soon
 * as there were more than about six. Anchoring by which side of the ring a node sits on
 * pushes every label away from its neighbours instead of into them.
 */
function DomainGraph({ domains, edges }: {
  domains: Record<string, string[]>;
  edges: { from: string; to: string }[];
}) {
  const names = Object.keys(domains);
  if (!names.length) return <p className="empty">No domain structure detected.</p>;

  const MAX_LABEL = 18;
  // A ring in a fixed viewport holds about twenty labels. Beyond that the radius is
  // capped by width, so growing the diagram does nothing and the labels simply collide.
  // Rather than render mush, label the domains that carry the most structure and leave
  // the rest as dots — every circle still names itself on hover, and the caption says
  // plainly how many are unlabelled. A readable partial view beats an unreadable whole.
  const MAX_LABELLED = 20;
  // Spread the candidates evenly around the ring first — picking the twenty
  // most-connected sounds better and is worse, since nothing stops them being
  // neighbours.
  const stride = Math.ceil(names.length / MAX_LABELLED);
  const single = names.length === 1;
  // Room for a label on each side, and vertical room that grows with the count so a
  // large estate spreads out instead of crowding.
  const W = 720;
  const H = Math.max(260, Math.min(560, 200 + names.length * 26));
  const cx = W / 2;
  const cy = H / 2;
  const r = Math.min(W / 2 - 170, H / 2 - 46);

  const nodes = names.map((n, i) => {
    const a = (i / names.length) * Math.PI * 2 - Math.PI / 2;
    const cos = single ? 0 : Math.cos(a);
    const sin = single ? 0 : Math.sin(a);
    const x = single ? cx : cx + r * cos;
    const y = single ? cy : cy + r * sin;
    // Right of the ring reads left-to-right, left of it right-to-left, poles stay
    // centred — so text always grows away from the diagram, never across it.
    const anchor: 'start' | 'end' | 'middle' =
      cos > 0.25 ? 'start' : cos < -0.25 ? 'end' : 'middle';
    // Past ~20 domains the ring stops growing (the height is capped) and neighbouring
    // labels start to touch. Pushing every other one further out doubles the effective
    // gap between adjacent labels without making the diagram any taller.
    // Alternate on the LABEL sequence, not the node index: with a stride every
    // labelled node has an even index, so keying off `i % 2` staggered nothing.
    const pad = names.length > 12 && Math.floor(i / stride) % 2 === 1 ? 38 : 17;
    return {
      n, x, y, anchor,
      lx: x + cos * pad + (anchor === 'middle' ? 0 : cos > 0 ? 4 : -4),
      ly: y + sin * pad + (anchor === 'middle' ? (sin >= 0 ? 15 : -8) : 4),
      label: n.length > MAX_LABEL ? n.slice(0, MAX_LABEL - 1) + '…' : n,
      truncated: n.length > MAX_LABEL,
      candidate: i % stride === 0,
    };
  });

  // Then place them greedily and drop anything that would still collide. Every
  // heuristic tried before this (stagger, stride, a taller viewBox) left a handful of
  // sizes overlapping, because ring geometry does not divide evenly. Measuring the box
  // and rejecting is the only version that is actually true at every size — and a
  // dropped label costs a hover, while an overlapping one costs both names.
  const CH = 6.2, LINE = 14;                       // 10.5px semibold sans, measured
  const placed: { x0: number; x1: number; y0: number; y1: number }[] = [];
  const show = new Set<string>();
  for (const d of nodes) {
    if (!d.candidate) continue;
    const w = d.label.length * CH;
    const x0 = d.anchor === 'start' ? d.lx : d.anchor === 'end' ? d.lx - w : d.lx - w / 2;
    const box = { x0, x1: x0 + w, y0: d.ly - LINE * 0.75, y1: d.ly + LINE * 0.3 };
    if (box.x0 < 2 || box.x1 > W - 2) continue;    // would run off the edge
    if (placed.some((b) => box.x0 < b.x1 && b.x0 < box.x1 && box.y0 < b.y1 && b.y0 < box.y1)) continue;
    placed.push(box);
    show.add(d.n);
  }
  const hidden = names.length - show.size;
  const pos: Record<string, (typeof nodes)[number]> =
    Object.fromEntries(nodes.map((d) => [d.n, d]));

  return (
    <>
    <svg className="domgraph" viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
      aria-label={`${names.length} domains and their dependencies`}>
      <defs>
        <marker id="dgArrow" markerWidth="7" markerHeight="7" refX="16" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6" fill="none" stroke="var(--border-strong)" strokeWidth="1.2" />
        </marker>
      </defs>
      {edges.filter((e) => pos[e.from] && pos[e.to]).map((e, i) => (
        <line key={i} x1={pos[e.from].x} y1={pos[e.from].y} x2={pos[e.to].x} y2={pos[e.to].y}
          stroke="var(--border-strong)" strokeWidth={1.2} markerEnd="url(#dgArrow)" />
      ))}
      {nodes.map((d) => (
        <g key={d.n}>
          <circle cx={d.x} cy={d.y} r={11} fill="var(--panel-3)" stroke="var(--teal)" strokeWidth={1.4}>
            <title>{`${d.n} — ${(domains[d.n] || []).length} class(es)`}</title>
          </circle>
          <text x={d.x} y={d.y + 3.5} textAnchor="middle" className="dg-count num">
            {(domains[d.n] || []).length}
          </text>
          {show.has(d.n) && (
            <text x={d.lx} y={d.ly} textAnchor={d.anchor} className="dg-name">
              {d.label}
              {/* Truncation must not lose the name — the full one stays on hover. */}
              {d.truncated && <title>{d.n}</title>}
            </text>
          )}
        </g>
      ))}
    </svg>
    {hidden > 0 && (
      <p className="dg-note">
        {show.size} of {names.length} domains are labelled — the rest are drawn
        unlabelled to keep the names legible. Hover any circle for its name.
      </p>
    )}
    </>
  );
}


/** Real folder tree of everything the scan saw. */
function FileTree({ files }: { files: { path: string; bytes: number }[] }) {
  const [open, setOpen] = useState<Set<string>>(new Set(['']));
  const root = useMemo(() => {
    const r: any = { name: '', dirs: new Map(), files: [] };
    for (const f of files) {
      const parts = f.path.split('/');
      let node = r;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!node.dirs.has(parts[i])) node.dirs.set(parts[i], { name: parts[i], dirs: new Map(), files: [] });
        node = node.dirs.get(parts[i]);
      }
      node.files.push({ name: parts[parts.length - 1], bytes: f.bytes });
    }
    return r;
  }, [files]);

  const render = (node: any, path: string, depth: number): any => {
    const isOpen = open.has(path);
    return (
      <div key={path || 'root'}>
        {depth > 0 && (
          <div className="tree-row dir" style={{ paddingLeft: depth * 14 }}
            onClick={() => setOpen((s) => { const n = new Set(s); n.has(path) ? n.delete(path) : n.add(path); return n; })}>
            <span className="tw">{isOpen ? '▾' : '▸'}</span>📁 {node.name}
            <span className="tree-meta num">{node.files.length + node.dirs.size}</span>
          </div>
        )}
        {(depth === 0 || isOpen) && (
          <>
            {[...node.dirs.values()].map((c: any) => render(c, path ? `${path}/${c.name}` : c.name, depth + 1))}
            {node.files.map((f: any) => (
              <div className="tree-row" key={path + f.name} style={{ paddingLeft: (depth + 1) * 14 }}>
                <span className="tw" />{fileIcon(f.name)} {f.name}
                <span className="tree-meta num">{(f.bytes / 1024).toFixed(1)} KB</span>
              </div>
            ))}
          </>
        )}
      </div>
    );
  };
  return <div className="tree">{render(root, '', 0)}</div>;
}

const fileIcon = (n: string) =>
  n.endsWith('.java') ? '☕' : n.endsWith('.ts') ? '🅃' : n.endsWith('.html') ? '🖹'
    : n.endsWith('.xml') ? '⚙' : n.endsWith('.impex') ? '🗒' : n.match(/\.s?css$/) ? '🎨' : '📄';
