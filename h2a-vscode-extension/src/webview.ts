import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

export class WebviewPanelProvider {
    public static currentPanel: WebviewPanelProvider | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private readonly _extensionUri: vscode.Uri;
    private _disposables: vscode.Disposable[] = [];

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, logContent: string, callGraphJson: string, resultsJson: string) {
        this._panel = panel;
        this._extensionUri = extensionUri;

        // Set the webview's initial html content
        this._update(logContent, callGraphJson, resultsJson);

        // Listen for when the panel is disposed
        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
    }

    // Read the generated Salesforce project + reports so the webview can render the
    // migration RESULT (ledger, reports, Apex + LWC files) — not just the console log.
    private static _collectResults(outputPath: string): string {
        const reportFiles = ['MIGRATION_PLAN.md', 'FEASIBILITY_REPORT.md', 'PARITY.md',
                             'DATA_MIGRATION.md', 'CRON_JOBS.md', 'MAPPING.md'];
        const reports: { name: string, text: string }[] = [];
        for (const r of reportFiles) {
            const p = path.join(outputPath, r);
            if (fs.existsSync(p)) {
                try { reports.push({ name: r, text: fs.readFileSync(p, 'utf8') }); } catch (e) { /* skip */ }
            }
        }
        const apex: string[] = [], lwc: string[] = [], data: string[] = [];
        const classesDir = path.join(outputPath, 'force-app', 'main', 'default', 'classes');
        if (fs.existsSync(classesDir)) {
            try { for (const f of fs.readdirSync(classesDir)) { if (f.endsWith('.cls')) apex.push(f); } } catch (e) { /* skip */ }
        }
        const lwcDir = path.join(outputPath, 'force-app', 'main', 'default', 'lwc');
        if (fs.existsSync(lwcDir)) {
            try {
                for (const d of fs.readdirSync(lwcDir)) {
                    if (fs.statSync(path.join(lwcDir, d)).isDirectory()) { lwc.push(d); }
                }
            } catch (e) { /* skip */ }
        }
        const dataDir = path.join(outputPath, 'data');
        if (fs.existsSync(dataDir)) {
            try { for (const f of fs.readdirSync(dataDir)) { if (f.endsWith('.csv')) data.push(f); } } catch (e) { /* skip */ }
        }
        return JSON.stringify({ reports, files: { apex, lwc, data } });
    }

    public static createOrShow(extensionUri: vscode.Uri, logContent: string, outputPath: string) {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;

        let callGraphJson = '{"nodes": [], "links": []}';
        const callGraphPath = path.join(outputPath, '.call_graph.json');
        if (fs.existsSync(callGraphPath)) {
            try {
                callGraphJson = fs.readFileSync(callGraphPath, 'utf8');
            } catch (e) {
                console.error('Failed to read call graph:', e);
            }
        }

        const resultsJson = WebviewPanelProvider._collectResults(outputPath);

        if (WebviewPanelProvider.currentPanel) {
            WebviewPanelProvider.currentPanel._panel.reveal(column);
            WebviewPanelProvider.currentPanel._update(logContent, callGraphJson, resultsJson);
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'h2aStatus',
            'H2A Converter Logs',
            column || vscode.ViewColumn.One,
            {
                enableScripts: true,
                localResourceRoots: [extensionUri]
            }
        );

        WebviewPanelProvider.currentPanel = new WebviewPanelProvider(panel, extensionUri, logContent, callGraphJson, resultsJson);
    }

    private _update(logContent: string, callGraphJson: string, resultsJson: string) {
        this._panel.title = 'H2A Translation Status';
        this._panel.webview.html = this._getHtmlForWebview(logContent, callGraphJson, resultsJson);
    }

    private _getHtmlForWebview(logContent: string, callGraphJson: string, resultsJson: string): string {
        // Parse logs to extract metrics for the dashboard
        const completenessMatch = logContent.match(/Completeness:\s*(.+)/);
        const completeness = completenessMatch ? completenessMatch[1].trim() : "";
        const requestsMatch = logContent.match(/requests=(\d+)/);
        const promptTokensMatch = logContent.match(/prompt_tokens=(\d+)/);
        const completionTokensMatch = logContent.match(/completion_tokens=(\d+)/);
        const detectedDomainsMatch = logContent.match(/Detected Domains:\s*\[(.*?)\]/);
        const topoOrderMatch = logContent.match(/Topological Execution Order:\s*\[(.*?)\]/);
        const skippedDomainsMatch = logContent.match(/Skipped domains\s*\(\d+\):\s*\[(.*?)\]/);

        const requests = requestsMatch ? requestsMatch[1] : "0";
        const promptTokens = promptTokensMatch ? promptTokensMatch[1] : "0";
        const completionTokens = completionTokensMatch ? completionTokensMatch[1] : "0";
        
        let detectedDomains: string[] = [];
        if (detectedDomainsMatch && detectedDomainsMatch[1].trim()) {
            detectedDomains = detectedDomainsMatch[1].split(',').map(s => s.replace(/['"\s]/g, ''));
        }
        
        let topoOrder: string[] = [];
        if (topoOrderMatch && topoOrderMatch[1].trim()) {
            topoOrder = topoOrderMatch[1].split(',').map(s => s.replace(/['"\s]/g, ''));
        }

        let skippedDomains: string[] = [];
        if (skippedDomainsMatch && skippedDomainsMatch[1].trim()) {
            skippedDomains = skippedDomainsMatch[1].split(',').map(s => s.replace(/['"\s]/g, ''));
        }

        const successCount = topoOrder.length - skippedDomains.length;
        const statusText = skippedDomains.length === 0 ? "SUCCESS" : (successCount > 0 ? "PARTIAL SUCCESS" : "FAILED");
        const statusClass = skippedDomains.length === 0 ? "status-success" : (successCount > 0 ? "status-warning" : "status-failed");

        const formattedLogs = logContent
            .replace(/\n/g, '<br>')
            .replace(/(✓\s+.*?)(?=<br>)/g, '<span class="log-success">$1</span>')
            .replace(/(⚠\s+.*?)(?=<br>)/g, '<span class="log-warning">$1</span>')
            .replace(/(🔍\s+.*?)(?=<br>)/g, '<span class="log-info">$1</span>')
            .replace(/═══(.*?)═══/g, '<span class="log-divider">═══ $1 ═══</span>');

        // Generate Pipeline Stepper HTML
        const stepsHtml = topoOrder.map(domain => {
            const isSkipped = skippedDomains.includes(domain);
            const statusIcon = isSkipped ? "✕" : "✓";
            const stepClass = isSkipped ? "step-skipped" : "step-completed";
            return `
                <div class="step-card ${stepClass}">
                    <div class="step-icon">${statusIcon}</div>
                    <div class="step-details">
                        <div class="step-name">${domain}</div>
                        <div class="step-status">${isSkipped ? 'Skipped/Errors' : 'Migrated Successfully'}</div>
                    </div>
                </div>
            `;
        }).join('');

        return `<!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>H2A Migration Status</title>
                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
                <style>
                    :root {
                        --glass-bg: rgba(30, 30, 30, 0.45);
                        --glass-border: rgba(255, 255, 255, 0.08);
                        --glow-color: rgba(55, 148, 255, 0.15);
                        --text-primary: #ffffff;
                        --text-secondary: #a0aec0;
                        --color-success: #4ec9b0;
                        --color-warning: #ffb347;
                        --color-failed: #ff6b6b;
                        --color-info: #569cd6;
                    }
                    body {
                        font-family: 'Outfit', sans-serif;
                        padding: 30px;
                        color: var(--text-primary);
                        background: radial-gradient(circle at top right, rgba(29, 78, 216, 0.15), transparent 450px),
                                    radial-gradient(circle at bottom left, rgba(16, 185, 129, 0.06), transparent 400px),
                                    #121214;
                        margin: 0;
                        min-height: 100vh;
                        box-sizing: border-box;
                    }
                    .header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 30px;
                    }
                    .header h1 {
                        font-weight: 700;
                        font-size: 28px;
                        margin: 0;
                        background: linear-gradient(135deg, #60a5fa, #34d399);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        letter-spacing: -0.5px;
                    }
                    .status-badge {
                        padding: 8px 16px;
                        border-radius: 30px;
                        font-weight: 600;
                        font-size: 13px;
                        letter-spacing: 0.5px;
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
                        backdrop-filter: blur(5px);
                    }
                    .status-success {
                        background: rgba(78, 201, 176, 0.15);
                        border: 1px solid rgba(78, 201, 176, 0.3);
                        color: var(--color-success);
                    }
                    .status-warning {
                        background: rgba(255, 179, 71, 0.15);
                        border: 1px solid rgba(255, 179, 71, 0.3);
                        color: var(--color-warning);
                    }
                    .status-failed {
                        background: rgba(255, 107, 107, 0.15);
                        border: 1px solid rgba(255, 107, 107, 0.3);
                        color: var(--color-failed);
                    }
                    .dashboard-grid {
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                        gap: 20px;
                        margin-bottom: 30px;
                    }
                    .card {
                        background: var(--glass-bg);
                        border: 1px solid var(--glass-border);
                        border-radius: 16px;
                        padding: 20px;
                        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
                        backdrop-filter: blur(12px);
                        position: relative;
                        overflow: hidden;
                    }
                    .card::before {
                        content: '';
                        position: absolute;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: radial-gradient(circle at top left, var(--glow-color), transparent 60%);
                        pointer-events: none;
                    }
                    .card-label {
                        font-size: 13px;
                        font-weight: 500;
                        color: var(--text-secondary);
                        text-transform: uppercase;
                        letter-spacing: 0.8px;
                        margin-bottom: 8px;
                    }
                    .card-value {
                        font-size: 26px;
                        font-weight: 700;
                        letter-spacing: -0.5px;
                    }
                    .pipeline-section {
                        margin-bottom: 40px;
                    }
                    .section-title {
                        font-weight: 600;
                        font-size: 18px;
                        margin-bottom: 20px;
                        color: var(--text-secondary);
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }
                    .stepper-container {
                        display: flex;
                        flex-direction: column;
                        gap: 12px;
                    }
                    .step-card {
                        background: rgba(255, 255, 255, 0.02);
                        border: 1px solid rgba(255, 255, 255, 0.05);
                        border-radius: 12px;
                        padding: 15px 20px;
                        display: flex;
                        align-items: center;
                        gap: 16px;
                        transition: all 0.2s ease;
                    }
                    .step-card:hover {
                        background: rgba(255, 255, 255, 0.04);
                        border-color: rgba(255, 255, 255, 0.08);
                    }
                    .step-icon {
                        width: 32px;
                        height: 32px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: bold;
                        font-size: 14px;
                    }
                    .step-completed .step-icon {
                        background: rgba(78, 201, 176, 0.15);
                        border: 1px solid var(--color-success);
                        color: var(--color-success);
                    }
                    .step-skipped .step-icon {
                        background: rgba(255, 107, 107, 0.15);
                        border: 1px solid var(--color-failed);
                        color: var(--color-failed);
                    }
                    .step-name {
                        font-weight: 600;
                        font-size: 15px;
                    }
                    .step-status {
                        font-size: 12px;
                        color: var(--text-secondary);
                        margin-top: 2px;
                    }
                    /* Tab visualizer styling */
                    .visualizer-tabs {
                        display: flex;
                        gap: 10px;
                        margin-bottom: 15px;
                    }
                    .tab-btn {
                        background: rgba(255, 255, 255, 0.03);
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        color: var(--text-secondary);
                        padding: 8px 16px;
                        border-radius: 8px;
                        font-weight: 600;
                        font-size: 13px;
                        cursor: pointer;
                        transition: all 0.2s ease;
                    }
                    .tab-btn.active {
                        background: rgba(55, 148, 255, 0.15);
                        border-color: var(--color-info);
                        color: var(--text-primary);
                        box-shadow: 0 0 10px rgba(55, 148, 255, 0.25);
                    }
                    .canvas-container {
                        background: rgba(13, 13, 15, 0.8);
                        border: 1px solid rgba(255, 255, 255, 0.05);
                        border-radius: 16px;
                        padding: 15px;
                        position: relative;
                        overflow: hidden;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                    }
                    #graphCanvas {
                        width: 100%;
                        max-width: 800px;
                        height: 400px;
                        background: #09090b;
                        border-radius: 8px;
                        cursor: grab;
                    }
                    #graphCanvas:active {
                        cursor: grabbing;
                    }
                    .graph-tooltip {
                        margin-top: 10px;
                        font-size: 12px;
                        color: var(--text-secondary);
                        background: rgba(255,255,255,0.02);
                        padding: 4px 12px;
                        border-radius: 20px;
                        border: 1px solid rgba(255,255,255,0.05);
                        text-align: center;
                        min-height: 18px;
                    }
                    .console-section {
                        margin-top: 30px;
                    }
                    .console-viewport {
                        background-color: #0d0d0f;
                        border: 1px solid rgba(255, 255, 255, 0.05);
                        border-radius: 16px;
                        font-family: 'JetBrains Mono', monospace;
                        padding: 24px;
                        max-height: 400px;
                        overflow-y: auto;
                        font-size: 13px;
                        line-height: 1.6;
                        box-shadow: inset 0 2px 8px rgba(0,0,0,0.8);
                    }
                    .log-success { color: var(--color-success); }
                    .log-warning { color: var(--color-warning); }
                    .log-info { color: var(--color-info); }
                    .log-divider {
                        color: var(--text-secondary);
                        display: block;
                        margin: 20px 0 10px 0;
                        font-weight: bold;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                        padding-bottom: 5px;
                    }
                    ::-webkit-scrollbar {
                        width: 8px;
                        height: 8px;
                    }
                    ::-webkit-scrollbar-track {
                        background: rgba(0, 0, 0, 0.1);
                    }
                    ::-webkit-scrollbar-thumb {
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 10px;
                    }
                    ::-webkit-scrollbar-thumb:hover {
                        background: rgba(255, 255, 255, 0.2);
                    }
                    /* Migration result / reports / files */
                    .ledger-chips { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
                    .chip { padding: 5px 14px; border-radius: 30px; font-size: 13px; font-weight: 600;
                        border: 1px solid var(--glass-border); background: var(--glass-bg); }
                    .chip.converted { color: var(--color-success); border-color: rgba(78,201,176,0.35); }
                    .chip.flagged { color: var(--color-warning); border-color: rgba(255,179,71,0.35); }
                    .chip.skipped { color: var(--text-secondary); }
                    .chip.unaccounted { color: var(--color-failed); border-color: rgba(255,107,107,0.35); }
                    .file-summary { display: flex; gap: 18px; flex-wrap: wrap; color: var(--text-secondary); font-size: 13px; }
                    .file-summary b { color: var(--text-primary); }
                    .files-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 6px; }
                    .file-item { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-secondary);
                        padding: 4px 8px; background: rgba(255,255,255,0.03); border-radius: 5px; }
                    .file-item.lwc { color: var(--color-info); }
                    .report-view { background: rgba(0,0,0,0.25); border: 1px solid var(--glass-border);
                        border-radius: 10px; padding: 18px 22px; max-height: 520px; overflow: auto;
                        font-size: 13.5px; line-height: 1.6; }
                    .report-view h1 { font-size: 20px; border-bottom: 2px solid rgba(78,201,176,0.4); padding-bottom: 6px; }
                    .report-view h2 { font-size: 16px; margin-top: 22px; border-bottom: 1px solid var(--glass-border); padding-bottom: 5px; }
                    .report-view h3 { font-size: 14px; margin-top: 16px; color: var(--color-info); }
                    .report-view table { width: 100%; border-collapse: collapse; margin: 8px 0 14px; font-size: 12.5px; }
                    .report-view th, .report-view td { text-align: left; padding: 6px 9px; border-bottom: 1px solid var(--glass-border); vertical-align: top; }
                    .report-view th { color: var(--text-secondary); text-transform: uppercase; font-size: 11px; }
                    .report-view code { font-family: 'JetBrains Mono', monospace; font-size: 12px;
                        background: rgba(255,255,255,0.08); padding: 1px 5px; border-radius: 4px; }
                    .report-view ul { padding-left: 20px; }
                    .report-view blockquote { border-left: 3px solid var(--color-warning); margin: 8px 0;
                        padding: 4px 12px; color: var(--color-warning); background: rgba(255,179,71,0.08); }
                    .report-view hr { border: none; border-top: 1px solid var(--glass-border); margin: 16px 0; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>H2A Converter Dashboard</h1>
                    <div class="status-badge ${statusClass}">${statusText}</div>
                </div>

                <div class="dashboard-grid">
                    <div class="card">
                        <div class="card-label">Domains Tracked</div>
                        <div class="card-value">${topoOrder.length}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Success Rate</div>
                        <div class="card-value">${topoOrder.length > 0 ? Math.round((successCount / topoOrder.length) * 100) : 0}%</div>
                    </div>
                    <div class="card">
                        <div class="card-label">LLM API Calls</div>
                        <div class="card-value">${requests}</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Tokens Spent</div>
                        <div class="card-value">${(parseInt(promptTokens) + parseInt(completionTokens)).toLocaleString()}</div>
                    </div>
                </div>

                <div class="pipeline-section">
                    <div class="section-title">Method Call Graph & Data Flow</div>
                    <div class="visualizer-tabs">
                        <button id="tabBtnHybris" class="tab-btn active" onclick="switchTab('hybris')">SAP Hybris Call Flow</button>
                        <button id="tabBtnSalesforce" class="tab-btn" onclick="switchTab('salesforce')">Salesforce Apex fflib Flow</button>
                    </div>
                    <div class="canvas-container">
                        <canvas id="graphCanvas" width="800" height="400"></canvas>
                        <div id="graphTooltip" class="graph-tooltip">Hover over a method node to trace its data flow path</div>
                    </div>
                </div>

                ${topoOrder.length > 0 ? `
                <div class="pipeline-section">
                    <div class="section-title">
                        <span>Topological Compilation Sequence</span>
                    </div>
                    <div class="stepper-container">
                        ${stepsHtml}
                    </div>
                </div>
                ` : ''}

                <div class="pipeline-section">
                    <div class="section-title">Migration Result</div>
                    <div id="ledgerChips" class="ledger-chips"></div>
                    <div id="fileSummary" class="file-summary"></div>
                </div>

                <div class="pipeline-section">
                    <div class="section-title">Reports</div>
                    <div id="reportTabs" class="visualizer-tabs"></div>
                    <div id="reportView" class="report-view">No reports were generated.</div>
                </div>

                <div class="pipeline-section">
                    <div class="section-title">Generated Files</div>
                    <div id="filesList" class="files-list"></div>
                </div>

                <div class="console-section">
                    <div class="section-title">Execution Console Output</div>
                    <div class="console-viewport">
                        ${formattedLogs}
                    </div>
                </div>

                <script>
                    const callGraphData = ${callGraphJson};
                    const resultsData = ${resultsJson};
                    const completenessStr = ${JSON.stringify(completeness)};
                    let activeTab = 'hybris';

                    // ── Migration result: completeness ledger chips + file counts ──
                    (function renderResult() {
                        const chips = document.getElementById('ledgerChips');
                        if (completenessStr) {
                            chips.innerHTML = completenessStr.split(',').map(function (part) {
                                const t = part.trim();
                                const kind = (t.split(' ')[1] || '').toLowerCase();
                                return '<span class="chip ' + kind + '">' + t + '</span>';
                            }).join('');
                        } else {
                            chips.innerHTML = '<span class="chip">run complete</span>';
                        }
                        const f = (resultsData.files) || { apex: [], lwc: [], data: [] };
                        document.getElementById('fileSummary').innerHTML =
                            '<span><b>' + f.apex.length + '</b> Apex classes</span>' +
                            '<span><b>' + f.lwc.length + '</b> LWC bundles</span>' +
                            '<span><b>' + f.data.length + '</b> data CSVs</span>';
                        const filesList = document.getElementById('filesList');
                        const items = f.apex.map(function (n) { return '<div class="file-item">' + n + '</div>'; })
                            .concat(f.lwc.map(function (n) { return '<div class="file-item lwc">lwc/' + n + '</div>'; }))
                            .concat(f.data.map(function (n) { return '<div class="file-item">data/' + n + '</div>'; }));
                        filesList.innerHTML = items.length ? items.join('') : '<div class="file-item">No files generated.</div>';
                    })();

                    // ── Reports: compact Markdown → HTML renderer (headings, tables, lists, code) ──
                    function mdEscape(s) {
                        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    }
                    function mdInline(s) {
                        s = mdEscape(s);
                        s = s.replace(/\`([^\`]+)\`/g, '<code>$1</code>');
                        s = s.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
                        s = s.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '$1');
                        return s;
                    }
                    function renderMarkdown(md) {
                        const lines = md.split('\\n');
                        let html = '', i = 0, inList = false, inCode = false;
                        function closeList() { if (inList) { html += '</ul>'; inList = false; } }
                        while (i < lines.length) {
                            let line = lines[i];
                            if (line.indexOf('\`\`\`') === 0) {
                                if (!inCode) { closeList(); html += '<pre><code>'; inCode = true; }
                                else { html += '</code></pre>'; inCode = false; }
                                i++; continue;
                            }
                            if (inCode) { html += mdEscape(line) + '\\n'; i++; continue; }
                            // GFM table: header row followed by a |---| separator
                            if (line.indexOf('|') === 0 && i + 1 < lines.length && /^\\|[\\s:|-]+\\|/.test(lines[i + 1])) {
                                closeList();
                                const header = line.split('|').slice(1, -1).map(function (c) { return '<th>' + mdInline(c.trim()) + '</th>'; }).join('');
                                html += '<table><thead><tr>' + header + '</tr></thead><tbody>';
                                i += 2;
                                while (i < lines.length && lines[i].indexOf('|') === 0) {
                                    const cells = lines[i].split('|').slice(1, -1).map(function (c) { return '<td>' + mdInline(c.trim()) + '</td>'; }).join('');
                                    html += '<tr>' + cells + '</tr>';
                                    i++;
                                }
                                html += '</tbody></table>';
                                continue;
                            }
                            const h = line.match(/^(#{1,4})\\s+(.*)$/);
                            if (h) { closeList(); html += '<h' + h[1].length + '>' + mdInline(h[2]) + '</h' + h[1].length + '>'; i++; continue; }
                            if (line.indexOf('> ') === 0) { closeList(); html += '<blockquote>' + mdInline(line.slice(2)) + '</blockquote>'; i++; continue; }
                            if (/^[-*]\\s+/.test(line.trim()) || /^\\s+[-*]\\s+/.test(line)) {
                                if (!inList) { html += '<ul>'; inList = true; }
                                html += '<li>' + mdInline(line.replace(/^\\s*[-*]\\s+/, '')) + '</li>'; i++; continue;
                            }
                            if (line.trim() === '---') { closeList(); html += '<hr>'; i++; continue; }
                            if (line.trim() === '') { closeList(); i++; continue; }
                            closeList(); html += '<p>' + mdInline(line) + '</p>'; i++;
                        }
                        closeList();
                        return html;
                    }
                    (function renderReports() {
                        const reports = (resultsData.reports) || [];
                        const tabs = document.getElementById('reportTabs');
                        const view = document.getElementById('reportView');
                        if (!reports.length) { tabs.style.display = 'none'; return; }
                        function show(idx) {
                            view.innerHTML = renderMarkdown(reports[idx].text);
                            Array.prototype.forEach.call(tabs.children, function (b, i) { b.classList.toggle('active', i === idx); });
                        }
                        reports.forEach(function (r, idx) {
                            const b = document.createElement('button');
                            b.className = 'tab-btn' + (idx === 0 ? ' active' : '');
                            b.textContent = r.name.replace('.md', '').replace(/_/g, ' ');
                            b.onclick = function () { show(idx); };
                            tabs.appendChild(b);
                        });
                        // Prefer the migration plan (has the ledger) first if present
                        const planIdx = reports.findIndex(function (r) { return r.name === 'MIGRATION_PLAN.md'; });
                        show(planIdx >= 0 ? planIdx : 0);
                    })();

                    const canvas = document.getElementById('graphCanvas');
                    const ctx = canvas.getContext('2d');
                    const tooltip = document.getElementById('graphTooltip');

                    let nodes = [];
                    let links = [];

                    function initializeGraph() {
                        nodes = callGraphData.nodes.map((node, i) => {
                            let xVal = 400;
                            if (node.layer === 'Controller') xVal = 100 + Math.random() * 40;
                            else if (node.layer === 'Facade') xVal = 250 + Math.random() * 40;
                            else if (node.layer === 'Service') xVal = 450 + Math.random() * 40;
                            else if (node.layer === 'DAO') xVal = 650 + Math.random() * 40;

                            return {
                                ...node,
                                x: xVal,
                                y: 100 + Math.random() * 200,
                                vx: 0,
                                vy: 0,
                                r: 12
                            };
                        });

                        links = callGraphData.links.map(link => {
                            const sourceNode = nodes.find(n => n.id === link.source);
                            const targetNode = nodes.find(n => n.id === link.target);
                            return {
                                source: sourceNode,
                                target: targetNode
                            };
                        }).filter(l => l.source && l.target);
                    }

                    initializeGraph();

                    const repelStrength = 1500;
                    const springStrength = 0.05;
                    const centerStrength = 0.02;
                    const decay = 0.85;

                    let selectedNode = null;
                    let hoveredNode = null;
                    let mouseX = 0;
                    let mouseY = 0;

                    canvas.addEventListener('mousemove', (e) => {
                        const rect = canvas.getBoundingClientRect();
                        mouseX = (e.clientX - rect.left) * (canvas.width / rect.width);
                        mouseY = (e.clientY - rect.top) * (canvas.height / rect.height);

                        if (selectedNode) {
                            selectedNode.x = mouseX;
                            selectedNode.y = mouseY;
                        } else {
                            hoveredNode = null;
                            for (let n of nodes) {
                                const dist = Math.hypot(n.x - mouseX, n.y - mouseY);
                                if (dist < n.r + 5) {
                                    hoveredNode = n;
                                    break;
                                }
                            }
                            
                            if (hoveredNode) {
                                let displayName = hoveredNode.id;
                                if (activeTab === 'salesforce') {
                                    displayName = toSalesforceName(hoveredNode.id);
                                }
                                tooltip.innerHTML = "Tracing active link: <strong>" + displayName + "</strong> (" + hoveredNode.layer + ")";
                            } else {
                                tooltip.innerText = "Hover over a method node to trace its data flow path";
                            }
                        }
                    });

                    canvas.addEventListener('mousedown', () => {
                        if (hoveredNode) {
                            selectedNode = hoveredNode;
                        }
                    });

                    window.addEventListener('mouseup', () => {
                        selectedNode = null;
                    });

                    function toSalesforceName(id) {
                        return id
                            .replace(/Controller\b/g, 'Resource')
                            .replace(/Facade\b/g, 'Service')
                            .replace(/Dao\b/g, 'Selector')
                            .replace(/DAO\b/g, 'Selector')
                            .replace(/Model\b/g, '__c')
                            .replace(/DTO\b/g, 'Wrapper');
                    }

                    function switchTab(tab) {
                        activeTab = tab;
                        document.getElementById('tabBtnHybris').classList.toggle('active', tab === 'hybris');
                        document.getElementById('tabBtnSalesforce').classList.toggle('active', tab === 'salesforce');
                        initializeGraph();
                    }

                    function simulate() {
                        for (let i = 0; i < nodes.length; i++) {
                            const n1 = nodes[i];
                            for (let j = i + 1; j < nodes.length; j++) {
                                const n2 = nodes[j];
                                const dx = n2.x - n1.x;
                                const dy = n2.y - n1.y;
                                const dist = Math.hypot(dx, dy) || 1;
                                if (dist < 150) {
                                    const force = repelStrength / (dist * dist);
                                    const fx = (dx / dist) * force;
                                    const fy = (dy / dist) * force;
                                    n1.vx -= fx;
                                    n1.vy -= fy;
                                    n2.vx += fx;
                                    n2.vy += fy;
                                }
                            }
                        }

                        for (let link of links) {
                            const dx = link.target.x - link.source.x;
                            const dy = link.target.y - link.source.y;
                            const dist = Math.hypot(dx, dy) || 1;
                            const force = (dist - 100) * springStrength;
                            const fx = (dx / dist) * force;
                            const fy = (dy / dist) * force;
                            link.source.vx += fx;
                            link.source.vy += fy;
                            link.target.vx -= fx;
                            link.target.vy -= fy;
                        }

                        for (let n of nodes) {
                            let targetX = 400;
                            if (n.layer === 'Controller') targetX = 150;
                            else if (n.layer === 'Facade') targetX = 300;
                            else if (n.layer === 'Service') targetX = 480;
                            else if (n.layer === 'DAO') targetX = 650;

                            n.vx += (targetX - n.x) * centerStrength;
                            n.vy += (200 - n.y) * centerStrength;
                        }

                        for (let n of nodes) {
                            if (n !== selectedNode) {
                                n.x += n.vx;
                                n.y += n.vy;
                                n.vx *= decay;
                                n.vy *= decay;
                                n.x = Math.max(n.r + 10, Math.min(canvas.width - n.r - 10, n.x));
                                n.y = Math.max(n.r + 10, Math.min(canvas.height - n.r - 10, n.y));
                            }
                        }
                    }

                    function draw() {
                        ctx.clearRect(0, 0, canvas.width, canvas.height);
                        ctx.strokeStyle = 'rgba(255,255,255,0.015)';
                        ctx.lineWidth = 1;
                        for (let x = 0; x < canvas.width; x += 40) {
                            ctx.beginPath();
                            ctx.moveTo(x, 0);
                            ctx.lineTo(x, canvas.height);
                            ctx.stroke();
                        }
                        for (let y = 0; y < canvas.height; y += 40) {
                            ctx.beginPath();
                            ctx.moveTo(0, y);
                            ctx.lineTo(canvas.width, y);
                            ctx.stroke();
                        }

                        ctx.lineWidth = 2;
                        for (let link of links) {
                            const isHighlighted = hoveredNode && (link.source === hoveredNode || link.target === hoveredNode);
                            ctx.strokeStyle = isHighlighted ? 'rgba(55, 148, 255, 0.8)' : 'rgba(255,255,255,0.08)';
                            ctx.beginPath();
                            ctx.moveTo(link.source.x, link.source.y);
                            ctx.lineTo(link.target.x, link.target.y);
                            ctx.stroke();

                            const angle = Math.atan2(link.target.y - link.source.y, link.target.x - link.source.x);
                            const arrowX = link.target.x - (link.target.r + 4) * Math.cos(angle);
                            const arrowY = link.target.y - (link.target.r + 4) * Math.sin(angle);
                            ctx.fillStyle = isHighlighted ? 'rgba(55, 148, 255, 0.8)' : 'rgba(255,255,255,0.2)';
                            ctx.beginPath();
                            ctx.moveTo(arrowX, arrowY);
                            ctx.lineTo(arrowX - 8 * Math.cos(angle - Math.PI/6), arrowY - 8 * Math.sin(angle - Math.PI/6));
                            ctx.lineTo(arrowX - 8 * Math.cos(angle + Math.PI/6), arrowY - 8 * Math.sin(angle + Math.PI/6));
                            ctx.closePath();
                            ctx.fill();
                        }

                        for (let n of nodes) {
                            let color = '#a0aec0';
                            if (n.layer === 'Controller') color = '#ffb347';
                            else if (n.layer === 'Facade') color = '#00f0ff';
                            else if (n.layer === 'Service') color = '#3794ff';
                            else if (n.layer === 'DAO') color = '#4ec9b0';

                            if (hoveredNode === n) { ctx.shadowBlur = 15; ctx.shadowColor = color; } else { ctx.shadowBlur = 0; }
                            ctx.fillStyle = color;
                            ctx.beginPath();
                            ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
                            ctx.fill();
                            ctx.shadowBlur = 0;
                            ctx.strokeStyle = '#18181b';
                            ctx.lineWidth = 3;
                            ctx.stroke();
                            ctx.fillStyle = '#e4e4e7';
                            ctx.font = '10px Outfit';
                            ctx.textAlign = 'center';
                            ctx.fillText(n.id.split('.').pop(), n.x, n.y - n.r - 4);
                            ctx.fillStyle = '#71717a';
                            ctx.font = '8px Outfit';
                            let clsLabel = n.class;
                            if (activeTab === 'salesforce') clsLabel = toSalesforceName(clsLabel);
                            ctx.fillText(clsLabel, n.x, n.y + n.r + 10);
                        }
                    }

                    function updateLoop() {
                        simulate();
                        draw();
                        requestAnimationFrame(updateLoop);
                    }

                    updateLoop();
                </script>
            </body>
            </html>`;
    }

    public dispose() {
        WebviewPanelProvider.currentPanel = undefined;

        this._panel.dispose();

        while (this._disposables.length) {
            const x = this._disposables.pop();
            if (x) {
                x.dispose();
            }
        }
    }
}
