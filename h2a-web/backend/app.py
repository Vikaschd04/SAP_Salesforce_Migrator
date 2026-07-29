"""
app.py — FastAPI backend for the H2A web dashboard.

Wraps the existing migration engine (via run_manager) and exposes it to the browser:
start a run, stream live agent events (SSE), browse the generated Salesforce project,
read reports, and download the deployable package. The extension and CLI keep using
the same engine unchanged — this is just a second front door.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import markdown as md
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, PlainTextResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from run_manager import start_run, get_run, list_runs, ENGINE_ROOT

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"        # built React cockpit
LEGACY_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"     # no-build fallback
FRONTEND_DIR = WEB_DIST if WEB_DIST.exists() else LEGACY_FRONTEND
REPO_ROOT = ENGINE_ROOT.parent
UPLOAD_ROOT = Path(tempfile.gettempdir()) / "h2a_web_uploads"
OUTPUT_ROOT = Path(tempfile.gettempdir()) / "h2a_web_outputs"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="H2A Migration Dashboard", version="0.1.0")

# Report files at the output root that the dashboard surfaces.
_REPORT_FILES = ["MIGRATION_PLAN.md", "FEASIBILITY_REPORT.md", "PARITY.md",
                 "DATA_MIGRATION.md", "CRON_JOBS.md", "MAPPING.md"]


# ── starting a run ────────────────────────────────────────────────────────────

@app.post("/api/runs")
async def create_run(
    provider: str = Form("mock"),
    engine: str = Form("agentic"),
    verify: bool = Form(False),
    supervised: bool = Form(False),
    input_path: str = Form(""),
    upload: UploadFile | None = File(None),
):
    """Start a migration from either a server-side path or an uploaded .zip."""
    if upload is not None and upload.filename:
        input_dir = _extract_upload(upload)
    elif input_path.strip():
        input_dir = _resolve_input_path(input_path.strip())
    else:
        raise HTTPException(400, "Provide input_path or upload a .zip")

    run = start_run(input_dir, str(OUTPUT_ROOT / _new_out_name(input_dir)),
                    provider=provider, engine=engine, verify=verify, supervised=supervised)
    return {"run_id": run.id, "status": run.status}


@app.post("/api/runs/{run_id}/gate")
async def api_gate(run_id: str, decision: dict):
    """Submit a review-gate decision (approve / plan overrides / rework feedback),
    which unblocks the paused engine thread and lets the migration continue."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if not run.submit_gate(decision):
        raise HTTPException(409, "no gate is currently open for this run")
    return {"ok": True}


def _resolve_input_path(p: str) -> str:
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / p).resolve()      # allow paths relative to the repo (e.g. Testing/…)
    if not path.exists() or not path.is_dir():
        raise HTTPException(400, f"Input path not found or not a directory: {path}")
    return str(path)


def _extract_upload(upload: UploadFile) -> str:
    dest = UPLOAD_ROOT / Path(upload.filename).stem
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    data = upload.file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # guard against zip-slip
            for member in zf.namelist():
                target = (dest / member).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    raise HTTPException(400, "Unsafe path in zip")
            zf.extractall(dest)
    except zipfile.BadZipFile:
        raise HTTPException(400, "Upload is not a valid .zip")
    # If the zip contained a single top folder, use it as the root.
    entries = [e for e in dest.iterdir() if not e.name.startswith("__MACOSX")]
    return str(entries[0]) if len(entries) == 1 and entries[0].is_dir() else str(dest)


def _new_out_name(input_dir: str) -> str:
    return f"out_{Path(input_dir).name}_{os.urandom(3).hex()}"


# ── run status + live events ──────────────────────────────────────────────────

@app.get("/api/runs")
async def api_list_runs():
    return {"runs": list_runs()}


@app.get("/api/runs/{run_id}")
async def api_run(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {**run.summary(), "events": run.events}


@app.get("/api/runs/{run_id}/stream")
async def api_stream(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")

    def gen():
        for ev in run.stream():
            yield f"data: {json.dumps(ev)}\n\n"
        yield f"data: {json.dumps({'type': 'stream_end', 'status': run.status})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── browsing the generated Salesforce project ─────────────────────────────────

@app.get("/api/runs/{run_id}/files")
async def api_files(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    out = Path(run.output_dir)
    if not out.exists():
        return {"files": [], "reports": []}
    files = []
    for base in ["force-app", "data"]:
        root = out / base
        if root.exists():
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    files.append(str(f.relative_to(out)))
    for extra in ["schedule.apex"]:
        if (out / extra).exists():
            files.append(extra)
    reports = [r for r in _REPORT_FILES if (out / r).exists()]
    return {"files": files, "reports": reports}


@app.get("/api/runs/{run_id}/file")
async def api_file(run_id: str, path: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    out = Path(run.output_dir).resolve()
    target = (out / path).resolve()
    if not str(target).startswith(str(out)) or not target.is_file():   # guard traversal
        raise HTTPException(404, "file not found")
    return PlainTextResponse(target.read_text(encoding="utf-8", errors="replace"))


_UNSAFE_HTML = re.compile(
    r"<\s*(script|style|iframe|object|embed|form)[^>]*>.*?<\s*/\s*\1\s*>"
    r"|<\s*(script|style|iframe|object|embed|form)[^>]*/?>"
    r"|\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE | re.DOTALL,
)


def _render_markdown(text: str) -> str:
    """Render a report's Markdown to HTML for the visual preview.

    Reports are engine-generated, but they interpolate names from uploaded code,
    so we strip any script/style/handler HTML after rendering as defense in depth.
    (Full multi-tenant hardening — a real sanitizer allow-list — is a
    productionization item; this is a single-user local dashboard.)
    """
    html = md.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "toc", "attr_list"],
        output_format="html5",
    )
    return _UNSAFE_HTML.sub("", html)


@app.get("/api/runs/{run_id}/report")
async def api_report(run_id: str, name: str):
    """Return a report rendered to HTML (visual preview) plus its raw Markdown."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if name not in _REPORT_FILES:                          # whitelist — reports only
        raise HTTPException(404, "unknown report")
    target = Path(run.output_dir) / name
    if not target.is_file():
        raise HTTPException(404, "report not available yet")
    raw = target.read_text(encoding="utf-8", errors="replace")
    return {"name": name, "html": _render_markdown(raw), "raw": raw}


@app.get("/api/runs/{run_id}/diff")
async def api_diff(run_id: str, target: str):
    """Original source (Java/Angular) paired with the generated Apex/LWC for one target,
    for the side-by-side Monaco diff review."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    bb = getattr(run, "bb", None)
    if bb is None:
        raise HTTPException(409, "diff available after the run completes")
    art = next((a for a in bb.artifacts if a.target_name == target), None)
    if art is None:
        raise HTTPException(404, "target not found")
    source = "\n\n".join(f"// ── {c.get('class_name', '')} ({c.get('layer', '')}) ──\n{c.get('source', '')}"
                         for c in art.source_classes)
    if art.is_lwc:
        generated = (art.lwc_bundle or {}).get("js", "")
        right_lang = "javascript"
    else:
        generated = art.main_class
        right_lang = "java"          # Apex highlights well as Java in Monaco
    return {"target": target, "is_lwc": art.is_lwc, "source": source, "generated": generated,
            "left_lang": "java", "right_lang": right_lang,
            "targets": [a.target_name for a in bb.artifacts]}


def _copilot_context(run) -> str:
    """A compact digest of the migration for grounding the Copilot's answers."""
    bb = getattr(run, "bb", None)
    if bb is None:
        return "The run has not finished yet, so only partial context is available."
    counts: dict = {}
    for r in bb.completeness_ledger():
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    lines = [f"Completeness: {counts}.", "Targets:"]
    for p in bb.plan:
        flag = f" [review: {p.native_recommendation}]" if p.native_recommendation else ""
        dec = "Skip" if p.target_kind == "Skip" else "Convert"
        lines.append(f"- {p.target_name} ({p.apex_pattern or p.layer}) -> {dec}{flag}; {p.rationale}")
    risks = [f"{n}: {r}" for n, u in bb.comprehensions.items()
             if isinstance(u, dict) for r in (u.get("migration_risks") or [])]
    if risks:
        lines += ["Migration risks:"] + [f"- {r}" for r in risks[:20]]
    findings = [f"{a.target_name}: [{f.get('severity')}] {f.get('message')}"
                for a in bb.artifacts for f in a.critic_findings]
    if findings:
        lines += ["Critic findings:"] + [f"- {f}" for f in findings[:20]]
    if bb.open_questions:
        lines += ["Open questions:"] + [f"- {q}" for q in bb.open_questions[:10]]
    return "\n".join(lines)


def _copilot_mock_answer(q: str, run) -> str:
    """Keyless, grounded answers from real run data so the Copilot is useful even in
    mock mode. Real providers get full natural-language answers via the LLM."""
    bb = getattr(run, "bb", None)
    if bb is None:
        return "I'll have the full picture once the run completes — start or finish a migration and ask again."
    ql = q.lower()
    counts: dict = {}
    for r in bb.completeness_ledger():
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    ledger_line = ", ".join(f"{v} {k}" for k, v in counts.items())
    if any(k in ql for k in ("risk", "danger", "careful", "gotcha")):
        risks = [f"• {n}: {r}" for n, u in bb.comprehensions.items()
                 if isinstance(u, dict) for r in (u.get("migration_risks") or [])]
        return "Migration risks I flagged:\n" + ("\n".join(risks[:15]) if risks
                else "None recorded — mock comprehension is sparse; run with Anthropic/OpenRouter for detailed risks.")
    if "skip" in ql:
        sk = [f"• {p.target_name}: {p.rationale}" for p in bb.plan if p.target_kind == "Skip"]
        sk += [f"• {s.get('class_name', '?')}: {s.get('reason', 'framework/type-only file — no business logic')}"
               for s in getattr(bb, "frontend_skipped", [])]
        return "Skipped (no business logic to convert):\n" + ("\n".join(sk) if sk
                else "Nothing was skipped — every target was converted.")
    if any(k in ql for k in ("flag", "native", "cpq", "review")):
        fl = [f"• {p.target_name}: consider {p.native_recommendation}" for p in bb.plan if p.native_recommendation]
        return "Flagged for native-product review (still fully converted):\n" + ("\n".join(fl) if fl
                else "No targets were flagged for a native product.")
    if any(k in ql for k in ("ledger", "complete", "summary", "coverage", "how many", "overview")):
        return (f"Completeness ledger: {ledger_line}. Every ingested class is accounted for — "
                "nothing was silently dropped.")
    if any(k in ql for k in ("finding", "critic", "issue", "error", "problem")):
        fs = [f"• {a.target_name}: [{f.get('severity')}] {f.get('message')}"
              for a in bb.artifacts for f in a.critic_findings]
        return "Critic findings:\n" + ("\n".join(fs[:15]) if fs
                else "The Critic found no blocking issues (mock review is conservative; a real provider reviews deeper).")
    if any(k in ql for k in ("lwc", "frontend", "spartacus", "angular", "component")):
        lw = [a.target_name for a in bb.artifacts if a.is_lwc]
        return "Frontend → LWC bundles generated: " + (", ".join(lw) if lw else "none in this codebase.")
    # class-specific?
    for a in bb.artifacts:
        if a.target_name.lower() in ql:
            notes = a.mapping_notes or "converted to Apex/LWC."
            flags = ("; ".join(a.review_flags)) if a.review_flags else "none"
            return f"{a.target_name} ({a.apex_pattern or a.layer}) — status {a.status}. {notes} Review flags: {flags}."
    return (f"Migration at a glance: {ledger_line}; {len(bb.artifacts)} artifacts built. "
            "Ask me about risks, skipped or flagged targets, Critic findings, LWC bundles, or a specific class. "
            "(Keyless mock Copilot — switch Provider to Anthropic/OpenRouter for full conversational answers.)")


@app.post("/api/runs/{run_id}/copilot")
async def api_copilot(run_id: str, body: dict):
    """Migration Copilot — ask questions about the run in natural language."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    question = (body.get("message") or "").strip()
    if not question:
        raise HTTPException(400, "empty message")
    # Answer with the SAME provider the run used (not the global config default) —
    # after a run finishes H2A_PROVIDER is cleared, so we key off run.provider.
    provider = (run.provider or "mock").lower()
    if provider == "mock":
        return {"answer": _copilot_mock_answer(question, run), "provider": "mock"}
    from src.llm import call_llm   # engine on sys.path via run_manager
    system = ("You are the H2A Migration Copilot, an expert SAP Hybris to Salesforce architect. "
              "Answer concisely and specifically, grounded ONLY in the migration context provided. "
              "If asked to change something, explain precisely what you would do and why.")
    prompt = f"Migration context:\n{_copilot_context(run)}\n\nQuestion: {question}"
    prev = os.environ.get("H2A_PROVIDER")
    os.environ["H2A_PROVIDER"] = provider          # make the engine use the run's provider
    try:
        res = call_llm("copilot", prompt, 700, system_prompt=system)
        return {"answer": (res.get("content") or "").strip() or "(no answer)", "provider": provider}
    except Exception as e:
        raise HTTPException(500, f"copilot error: {e}")
    finally:
        if prev is None:
            os.environ.pop("H2A_PROVIDER", None)
        else:
            os.environ["H2A_PROVIDER"] = prev


@app.get("/api/runs/{run_id}/package")
async def api_package(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    out = Path(run.output_dir)
    if not out.exists():
        raise HTTPException(404, "no output yet")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out))
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{Path(out).name}.zip"'})


@app.get("/api/health")
async def health():
    return {"ok": True, "engine_root": str(ENGINE_ROOT)}


# ── serve the dashboard (static, no build step) ───────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
