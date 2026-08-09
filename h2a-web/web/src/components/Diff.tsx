import { useEffect, useState } from 'react';
import { DiffEditor } from '@monaco-editor/react';
import '../monacoSetup';

interface DiffData { source: string; generated: string; left_lang: string; right_lang: string; is_lwc: boolean; }

export default function Diff({ runId, targets }: { runId: string; targets: string[] }) {
  const [target, setTarget] = useState(targets[0] || '');
  const [data, setData] = useState<DiffData | null>(null);
  const [loading, setLoading] = useState(false);
  const [wrap, setWrap] = useState(false);

  useEffect(() => {
    if (!target) return;
    setLoading(true);
    fetch(`/api/runs/${runId}/diff?target=${encodeURIComponent(target)}`)
      .then((r) => r.json()).then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [target, runId]);

  const theme = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'vs-dark';

  return (
    <div>
      <div className="chips-row" style={{ alignItems: 'center' }}>
        <select value={target} onChange={(e) => setTarget(e.target.value)}
          style={{ background: 'var(--panel)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 6, padding: '5px 9px', fontSize: 12 }}>
          {targets.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="faint" style={{ fontSize: 12 }}>
          ◄ Original source ({data?.is_lwc ? 'Angular' : 'Java'})&nbsp;&nbsp;·&nbsp;&nbsp;Generated ({data?.is_lwc ? 'LWC' : 'Apex'}) ►
        </span>
        <button className={`btn-mini ${wrap ? 'sel' : ''}`} onClick={() => setWrap((v) => !v)}
          title="Wrapping breaks line alignment; off means the panes scroll sideways">
          {wrap ? 'Wrapping' : 'No wrap'}
        </button>
      </div>
      {loading ? <p className="empty">Loading editor…</p> : data ? (
        <div style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
          <DiffEditor height="56vh" theme={theme}
            original={data.source || '// (no source captured)'} modified={data.generated || '// (empty)'}
            language={data.right_lang}
            options={{
              readOnly: true, renderSideBySide: true, minimap: { enabled: false },
              fontSize: 12, scrollBeyondLastLine: false, automaticLayout: true,
              // Wrapping a Java/Apex diff destroys line alignment, which is the whole
              // point of a side-by-side view — so it scrolls instead, and the bar is
              // sized to be noticed rather than hunted for.
              wordWrap: wrap ? 'on' : 'off',
              scrollbar: {
                horizontal: 'auto', horizontalScrollbarSize: 12,
                vertical: 'auto', verticalScrollbarSize: 12,
                alwaysConsumeMouseWheel: false,
              },
            }} />
        </div>
      ) : <p className="empty">Pick a target to diff.</p>}
    </div>
  );
}
