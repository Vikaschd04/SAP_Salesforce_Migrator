'use strict';
const $ = (s) => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m]));

const STAGES = [
  { id: 'analyze', n: 'Analyze' }, { id: 'comprehend', n: 'Comprehend' },
  { id: 'plan', n: 'Plan' }, { id: 'build', n: 'Build + Critic' },
  { id: 'reconcile', n: 'Reconcile + Write' }, { id: 'verify', n: 'Verify' },
];
let RUN = null, ES = null, ARTIFACTS = [], COMPREHENSIONS = [], DECISIONS = [];

// ── boot ──
function buildStepper() {
  const s = $('#stepper'); s.innerHTML = '';
  STAGES.forEach((st, i) => {
    const d = el('div', 'step'); d.id = 'step-' + st.id;
    d.innerHTML = `<div class="k">${String(i + 1).padStart(2, '0')}</div><div class="n">${st.n}</div><div class="d"></div>`;
    s.appendChild(d);
  });
}
function setStage(id, status, detail) {
  const d = $('#step-' + id); if (!d) return;
  d.classList.remove('active', 'done'); d.classList.add(status);
  if (detail) d.querySelector('.d').textContent = detail;
}
async function health() {
  try { const r = await (await fetch('/api/health')).json(); $('#health').textContent = r.ok ? 'engine ready' : 'engine ?'; }
  catch { $('#health').textContent = 'backend offline'; }
}

// ── tabs ──
$('#tabs').addEventListener('click', (e) => {
  const b = e.target.closest('.tab'); if (!b) return;
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t === b));
  document.querySelectorAll('.tabpanel').forEach((p) => p.classList.toggle('active', p.id === 'tab-' + b.dataset.tab));
});

// ── start a run ──
$('#startBtn').addEventListener('click', startRun);
async function startRun() {
  const btn = $('#startBtn'); btn.disabled = true; btn.textContent = 'Running…';
  resetUI();
  const fd = new FormData();
  fd.append('provider', $('#provider').value);
  fd.append('engine', $('#engine').value);
  fd.append('verify', $('#verify').checked);
  fd.append('supervised', $('#supervised').checked);
  const file = $('#uploadZip').files[0];
  if (file) fd.append('upload', file);
  else fd.append('input_path', $('#inputPath').value.trim());
  try {
    const res = await fetch('/api/runs', { method: 'POST', body: fd });
    if (!res.ok) { const t = await res.text(); throw new Error(t); }
    const { run_id } = await res.json();
    RUN = run_id;
    feed('system', 'Run started · ' + run_id, 'run_started');
    openStream(run_id);
  } catch (e) {
    feed('error', 'Failed to start: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = '▶ Start migration';
  }
}
function resetUI() {
  ARTIFACTS = []; COMPREHENSIONS = []; DECISIONS = []; buildStepper();
  $('#feed').innerHTML = ''; $('#elapsed').textContent = '';
  $('#tab-plan').innerHTML = '<p class="empty">Planner is deciding what to migrate…</p>';
  $('#tab-understanding').innerHTML = '<p class="empty">Comprehender is reading each class…</p>';
  $('#tab-artifacts').innerHTML = '<p class="empty">Waiting for the Builder…</p>';
  $('#tab-audit').innerHTML = '<p class="empty">Agent decisions will stream here…</p>';
  $('#filelist').innerHTML = '<li class="empty">Generated files appear after the run.</li>';
  $('#code').innerHTML = '<span class="empty">Select a file to view it.</span>';
  $('#ledgerBox').innerHTML = ''; $('#reportActions').innerHTML = '';
  $('#reportView').innerHTML = '<span class="empty">Reports appear when the run completes.</span>';
  if (ES) { ES.close(); ES = null; }
}

// ── live event stream ──
function openStream(id) {
  ES = new EventSource('/api/runs/' + id + '/stream');
  ES.onmessage = (m) => { try { handle(JSON.parse(m.data)); } catch {} };
  ES.onerror = () => { /* stream ends → server closes; onmessage stream_end handles UI */ };
}
function handle(ev) {
  if (ev.ts != null) $('#elapsed').textContent = ev.ts + 's';
  switch (ev.type) {
    case 'stage':
      setStage(ev.name, ev.status === 'done' ? 'done' : 'active', ev.detail || '');
      feed(ev.status === 'done' ? 'system' : 'active',
        (ev.status === 'done' ? '✓ ' : '▶ ') + cap(ev.name) + (ev.detail ? ' — ' + ev.detail : ''), 'stage');
      break;
    case 'analyzed':
      feed('Analyzer', `${ev.backend_classes} backend classes, ${ev.frontend_components} components, ${ev.objects} objects across ${ev.domains.length} domains`, 'plan');
      break;
    case 'comprehend': onComprehend(ev); break;
    case 'plan': renderPlan(ev.items); feed('Planner', `${ev.items.length} target(s) planned`, 'plan'); break;
    case 'artifact': onArtifact(ev); break;
    case 'critic_repair':
      feed('Critic ⇄ Builder', `${ev.target_name}: ${ev.errors} error(s) found → sent back to Builder, repaired & re-reviewed`
        + ((ev.categories && ev.categories.length) ? ' [' + ev.categories.join(', ') + ']' : ''), 'flag');
      break;
    case 'reconcile': onReconcile(ev); break;
    case 'decision': onDecision(ev); break;
    case 'gate_open': openGate(ev); break;
    case 'gate_closed': closeGate(); feed('system', 'Gate ' + esc(ev.gate) + ' → ' + esc(ev.action), 'stage'); break;
    case 'run_complete': onComplete(ev); break;
    case 'error': feed('error', ev.message, 'error'); finish(); break;
    case 'stream_end': finish(); break;
  }
}

// ── Human-in-the-loop review gates ──
function openGate(ev) {
  const overlay = $('#gateOverlay'), body = $('#gateBody'), actions = $('#gateActions');
  $('#gateSub').textContent = 'run ' + (RUN || '');
  actions.innerHTML = '';
  if (ev.gate === 'plan') {
    $('#gateTitle').textContent = 'Approve the migration plan';
    body.innerHTML = '<p class="gate-note">Review what each target does and its migration risk, then choose <b>Convert</b> or <b>Skip</b>. Flagged items (e.g. “consider CPQ”) are still converted — the flag is just a review note.</p>';
    const cards = ev.items.map((p) => {
      const c = p.comprehension || {};
      const flag = p.native_recommendation ? `<span class="badge b-flag">consider ${esc(p.native_recommendation)}</span>` : '';
      const rules = (c.business_rules || []).length
        ? `<div class="g-meta"><span class="u-lbl">Rules to preserve (${c.business_rules.length})</span><ul>${c.business_rules.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></div>` : '';
      const risks = (c.migration_risks || []).length
        ? `<div class="g-meta g-risk"><span class="u-lbl">⚠ Migration risks</span><ul>${c.migration_risks.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></div>` : '';
      return `<div class="g-item">
        <div class="g-item-head">
          <span class="a-name">${esc(p.target_name)}</span>
          <span class="badge">${esc(p.layer)}</span>${cxBadge(c.complexity)}${flag}
          <select data-t="${esc(p.target_name)}">
            <option value="Convert"${p.decision !== 'Skip' ? ' selected' : ''}>Convert</option>
            <option value="Skip"${p.decision === 'Skip' ? ' selected' : ''}>Skip</option>
          </select>
        </div>
        ${c.purpose ? `<p class="g-purpose">${esc(c.purpose)}</p>` : ''}
        ${rules}${risks}
        <div class="g-from">from ${esc((p.sources || []).join(', ') || '—')}</div>
      </div>`;
    }).join('');
    body.innerHTML += cards;
    const orig = {}; ev.items.forEach((p) => orig[p.target_name] = p.decision === 'Skip' ? 'Skip' : 'Convert');
    const go = el('button', 'go', 'Approve plan ▶');
    go.onclick = () => {
      const overrides = {};
      body.querySelectorAll('select[data-t]').forEach((s) => {
        if (s.value !== orig[s.dataset.t]) overrides[s.dataset.t] = { decision: s.value };
      });
      submitGate({ action: 'approve', overrides });
    };
    actions.appendChild(go);
  } else if (ev.gate === 'build') {
    $('#gateTitle').textContent = 'Review the generated code';
    body.innerHTML = '<p class="gate-note">Review each artifact. Approve everything, or type feedback on any file and send it back — the Builder will regenerate it addressing your note, the Critic re-reviews, then you review again.</p>';
    ev.artifacts.forEach((a) => {
      const kind = a.is_lwc ? 'LWC' : (a.apex_pattern || 'Apex');
      const badge = a.status === 'accepted' ? '<span class="badge b-accepted">accepted</span>' : `<span class="badge b-needs">${esc(a.status)}</span>`;
      const findings = (a.findings || []).map((f) => `${esc(f.severity)}: ${esc(f.message)}${f.suggestion ? ` — 💡 ${esc(f.suggestion)}` : ''}`).join('<br>') || 'none';
      const div = el('div', 'art-review');
      div.innerHTML = `<div class="ar-head"><span class="ar-name">${esc(a.target_name)} · ${esc(kind)}</span>${badge}</div>
        <div style="font-size:11.5px;color:var(--gray);margin-top:4px">Critic: ${findings}</div>
        <details><summary>view code</summary><pre>${esc(a.code || '(no preview)')}</pre></details>
        <textarea data-t="${esc(a.target_name)}" placeholder="Send back with feedback (leave empty to accept)…"></textarea>`;
      body.appendChild(div);
    });
    const approve = el('button', 'go', 'Approve all ▶');
    approve.onclick = () => submitGate({ action: 'approve' });
    const rework = el('button', 'warn', '↺ Send back & rebuild');
    rework.onclick = () => {
      const feedback = {};
      body.querySelectorAll('textarea[data-t]').forEach((t) => { if (t.value.trim()) feedback[t.dataset.t] = t.value.trim(); });
      if (!Object.keys(feedback).length) { submitGate({ action: 'approve' }); return; }
      submitGate({ action: 'rework', feedback });
    };
    actions.appendChild(rework); actions.appendChild(approve);
  }
  overlay.hidden = false;
}
function closeGate() { $('#gateOverlay').hidden = true; }
async function submitGate(decision) {
  closeGate();
  feed('Reviewer', decision.action === 'rework'
    ? 'sent ' + Object.keys(decision.feedback).length + ' file(s) back with feedback'
    : 'approved (' + (Object.keys(decision.overrides || {}).length || 0) + ' change(s))', 'stage');
  try { await fetch('/api/runs/' + RUN + '/gate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(decision) }); }
  catch (e) { feed('error', 'gate submit failed: ' + e.message, 'error'); }
}
function finish() {
  const btn = $('#startBtn'); btn.disabled = false; btn.textContent = '▶ Start migration';
  if (ES) { ES.close(); ES = null; }
}
const cap = (s) => s ? s[0].toUpperCase() + s.slice(1) : s;
function feed(agent, msg, kind) {
  const list = $('#feed'); if (list.querySelector('.empty')) list.innerHTML = '';
  const row = el('div', 'ev ' + (kind || ''));
  row.innerHTML = `<span class="t">${$('#elapsed').textContent || ''}</span><span class="b"><span class="agent">${esc(agent)}</span> ${esc(msg)}</span>`;
  list.appendChild(row); list.scrollTop = list.scrollHeight;
}

// ── Plan tab ──
function renderPlan(items) {
  const rows = items.map((p) => {
    const dec = p.decision === 'Skip'
      ? '<span class="badge b-skip">Skip</span>'
      : '<span class="badge b-convert">Convert</span>';
    const flag = p.native_recommendation
      ? `<span class="badge b-flag">consider ${esc(p.native_recommendation)}</span>` : '';
    return `<tr><td><code>${esc(p.target_name)}</code></td><td>${esc(p.layer)}</td>
      <td>${dec}</td><td>${flag}</td><td class="muted">${esc(p.rationale || '')}</td>
      <td>${esc((p.sources || []).join(', '))}</td></tr>`;
  }).join('');
  $('#tab-plan').innerHTML =
    `<table><thead><tr><th>Target</th><th>Type</th><th>Decision</th><th>Review flag</th><th>Why</th><th>From</th></tr></thead><tbody>${rows}</tbody></table>`;
}

// ── Understanding tab (what the AI comprehended about each class) ──
function onComprehend(ev) {
  COMPREHENSIONS.push(ev);
  const n = (ev.business_rules || []).length;
  feed('Comprehender', `${ev.cls} (${ev.layer})` + (ev.purpose ? ' — ' + ev.purpose : '')
    + (n ? ` · ${n} business rule${n === 1 ? '' : 's'} to preserve` : ''), 'plan');
  renderUnderstanding();
}
function cxBadge(cx) {
  if (!cx) return '';
  const k = cx.toLowerCase();
  return `<span class="badge cx-${esc(k)}">${esc(cx)} complexity</span>`;
}
function renderUnderstanding() {
  if (!COMPREHENSIONS.length) return;
  const sec = (label, arr, cls) => (arr && arr.length)
    ? `<div class="u-sec"><span class="u-lbl">${label}</span><ul class="${cls || ''}">${arr.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
  $('#tab-understanding').innerHTML = COMPREHENSIONS.map((c) => `<div class="u-card">
      <div class="u-head"><span class="u-name">${esc(c.cls)}</span><span class="badge">${esc(c.layer)}</span>${cxBadge(c.complexity)}</div>
      ${c.purpose ? `<p class="u-purpose">${esc(c.purpose)}</p>` : ''}
      ${sec('Business rules to preserve', c.business_rules)}
      ${sec('⚠ Migration risks', c.migration_risks, 'u-risks')}
      ${sec('Data it queries', c.queries)}
      ${sec('Depends on', c.dependencies)}
      ${sec('Side effects', c.side_effects)}
    </div>`).join('');
}

// ── Audit trail tab (live decisions timeline) ──
function onDecision(ev) {
  DECISIONS.push(ev);
  renderAudit();
}
function renderAudit() {
  if (!DECISIONS.length) return;
  $('#tab-audit').innerHTML = `<ol class="audit">` + DECISIONS.map((d) =>
    `<li class="au-row"><span class="au-agent">${esc(d.agent)}</span>
      <span class="au-act">${esc(d.action)}</span>
      <span class="au-detail">${esc(d.detail || '')}</span></li>`).join('') + `</ol>`;
  const box = $('#tab-audit'); box.scrollTop = box.scrollHeight;
}

// ── Reconcile: schema changes the AI made ──
function onReconcile(ev) {
  const nf = (ev.added_fields || []).length, no = (ev.added_objects || []).length;
  if (nf || no) feed('Reconciler', `schema augmented — +${no} object(s), +${nf} field(s), each evidence-backed`, 'flag');
}

// ── Artifacts tab (expandable: what the Builder mapped + every Critic finding) ──
const OPEN_ARTS = new Set();
function onArtifact(ev) {
  if (ev.status === 'building') {
    const why = ev.native_recommendation ? ` · flagged: consider ${ev.native_recommendation}` : '';
    feed('Builder', `building ${ev.target_name} as ${ev.apex_pattern || 'Apex'}`
      + (ev.sources && ev.sources.length ? ` from ${ev.sources.join(', ')}` : '') + why, 'build');
    return;
  }
  const idx = ARTIFACTS.findIndex((a) => a.target_name === ev.target_name);
  if (idx >= 0) ARTIFACTS[idx] = ev; else ARTIFACTS.push(ev);   // rework replaces the done entry
  const flagTxt = (ev.review_flags && ev.review_flags.length) ? ' · flagged' : '';
  const rw = ev.reworked ? ' (reworked)' : '';
  feed('Critic', `${ev.target_name} → ${ev.status}${rw}${flagTxt} (${ev.findings} finding${ev.findings === 1 ? '' : 's'})`,
    (ev.review_flags && ev.review_flags.length) ? 'flag' : 'build');
  renderArtifacts();
}
function renderArtifacts() {
  if (!ARTIFACTS.length) { $('#tab-artifacts').innerHTML = '<p class="empty">Waiting for the Builder…</p>'; return; }
  $('#tab-artifacts').innerHTML = ARTIFACTS.map((a) => {
    const open = OPEN_ARTS.has(a.target_name);
    const kb = a.is_lwc ? '<span class="badge b-lwc">LWC</span>' : `<span class="badge">${esc(a.apex_pattern || 'Apex')}</span>`;
    const sb = a.status === 'accepted' ? '<span class="badge b-accepted">accepted</span>' : `<span class="badge b-needs">${esc(a.status)}</span>`;
    const flags = (a.review_flags || []).map((f) => `<span class="badge b-flag">${esc(f)}</span>`).join(' ');
    const fnd = (a.findings_detail || []);
    const fndHtml = fnd.length
      ? fnd.map((f) => `<li class="fnd ${f.severity === 'ERROR' ? 'err' : 'warn'}"><span class="sev">${esc(f.severity)}</span> <span class="cat">${esc(f.category || '')}</span> ${esc(f.message || '')}${f.suggestion ? `<div class="fix">💡 <b>Fix:</b> ${esc(f.suggestion)}</div>` : ''}</li>`).join('')
      : '<li class="fnd ok">Critic clean — no findings</li>';
    const rules = (a.business_rules || []).map((r) => `<li>${esc(r)}</li>`).join('');
    const parts = (a.is_lwc && a.lwc_parts && a.lwc_parts.length)
      ? `<div class="a-sec"><span class="u-lbl">LWC bundle</span> ${a.lwc_parts.map((p) => `<code>${esc(p)}</code>`).join(' ')}${a.has_controller ? ' · <code>+Apex controller</code>' : ''}</div>` : '';
    const sobj = (a.sobject_refs && a.sobject_refs.length)
      ? `<div class="a-sec"><span class="u-lbl">SObjects</span> ${a.sobject_refs.map((s) => `<code>${esc(s)}</code>`).join(' ')}</div>` : '';
    return `<div class="a-card">
      <div class="a-head" data-name="${esc(a.target_name)}">
        <span class="tw">${open ? '▾' : '▸'}</span><span class="a-name">${esc(a.target_name)}</span>${kb}${sb} ${flags}
        <span class="a-count">${fnd.length} finding${fnd.length === 1 ? '' : 's'}</span>
      </div>
      <div class="a-body"${open ? '' : ' hidden'}>
        ${a.mapping_notes ? `<div class="a-sec"><span class="u-lbl">What was mapped</span><p class="muted">${esc(a.mapping_notes)}</p></div>` : ''}
        ${sobj}
        ${rules ? `<div class="a-sec"><span class="u-lbl">Business rules preserved</span><ul>${rules}</ul></div>` : ''}
        ${parts}
        <div class="a-sec"><span class="u-lbl">Critic findings</span><ul class="findings">${fndHtml}</ul></div>
      </div>
    </div>`;
  }).join('');
}
$('#tab-artifacts').addEventListener('click', (e) => {
  const head = e.target.closest('.a-head'); if (!head) return;
  const name = head.dataset.name;
  if (OPEN_ARTS.has(name)) OPEN_ARTS.delete(name); else OPEN_ARTS.add(name);
  const body = head.nextElementSibling, open = OPEN_ARTS.has(name);
  body.toggleAttribute('hidden', !open);
  head.querySelector('.tw').textContent = open ? '▾' : '▸';
});

// ── completion: ledger, files, reports ──
async function onComplete(ev) {
  STAGES.forEach((s) => { if (s.id !== 'verify' || $('#step-verify').classList.contains('active')) setStage(s.id, 'done'); });
  const sum = ev.ledger_summary || {};
  const chips = Object.entries(sum).map(([k, v]) => `<span class="chip c-${k}">${v} ${k}</span>`).join('');
  const ledgerRows = (ev.ledger || []).map((r) =>
    `<tr><td><code>${esc(r.source)}</code></td><td>${esc(r.layer)}</td>
      <td><span class="badge b-${r.outcome === 'skipped' ? 'skip' : r.outcome === 'flagged' ? 'flag' : r.outcome === 'unaccounted' ? 'needs' : 'convert'}">${esc(r.outcome)}</span></td>
      <td><code>${esc(r.target)}</code></td><td>${esc(r.note)}</td></tr>`).join('');
  $('#ledgerBox').innerHTML =
    `<h3 style="margin:0 0 8px;font-size:13px;text-transform:uppercase;color:var(--gray)">Completeness ledger</h3>
     <div class="ledger-summary">${chips || '<span class="chip">no data</span>'}</div>
     <table><thead><tr><th>Source</th><th>Layer</th><th>Outcome</th><th>Target</th><th>Note</th></tr></thead><tbody>${ledgerRows}</tbody></table>`;
  feed('system', 'Run complete — ' + (chips ? Object.entries(sum).map(([k, v]) => v + ' ' + k).join(', ') : ''), 'stage');
  await loadFiles(); await loadReports(ev);
  finish();
}

async function loadFiles() {
  try {
    const r = await (await fetch(`/api/runs/${RUN}/files`)).json();
    const list = $('#filelist');
    if (!r.files.length) { list.innerHTML = '<li class="empty">No files generated.</li>'; return; }
    list.innerHTML = '';
    r.files.forEach((f) => {
      const li = el('li', null, esc(f));
      li.onclick = () => selectFile(li, f);
      list.appendChild(li);
    });
  } catch {}
}
async function selectFile(li, path) {
  document.querySelectorAll('.filelist li').forEach((x) => x.classList.remove('sel'));
  li.classList.add('sel');
  try {
    const txt = await (await fetch(`/api/runs/${RUN}/file?path=${encodeURIComponent(path)}`)).text();
    $('#code').textContent = txt;
  } catch { $('#code').textContent = '// could not load file'; }
}
async function loadReports(ev) {
  const acts = $('#reportActions'); acts.innerHTML = '';
  const view = $('#reportView');
  let available = [];
  try { available = (await (await fetch(`/api/runs/${RUN}/files`)).json()).reports || []; } catch {}
  if (!available.length) {
    view.innerHTML = '<p class="empty">No reports were generated for this run.</p>';
  }
  let firstBtn = null;
  available.forEach((rep) => {
    const b = el('button', null, rep.replace('.md', '').replace(/_/g, ' '));
    b.dataset.rep = rep;
    b.onclick = () => showReport(rep, b);
    acts.appendChild(b);
    if (!firstBtn) firstBtn = b;
  });
  const dl = el('button', 'dl', '⬇ Download SFDX package');
  dl.onclick = () => window.location = `/api/runs/${RUN}/package`;
  acts.appendChild(dl);
  // auto-open the feasibility report (or the first available)
  const prefer = acts.querySelector('button[data-rep="FEASIBILITY_REPORT.md"]') || firstBtn;
  if (prefer) showReport(prefer.dataset.rep, prefer);
}

// Render one report as a visual HTML preview (not raw markdown).
async function showReport(name, btn) {
  document.querySelectorAll('#reportActions button[data-rep]')
    .forEach((b) => b.classList.toggle('sel', b === btn));
  const view = $('#reportView');
  view.innerHTML = '<p class="empty">Rendering…</p>';
  try {
    const r = await fetch(`/api/runs/${RUN}/report?name=${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    view.innerHTML = data.html && data.html.trim() ? data.html : '<p class="empty">(empty report)</p>';
    view.scrollTop = 0;
  } catch { view.innerHTML = '<p class="empty">(report not available)</p>'; }
}

buildStepper(); health();
