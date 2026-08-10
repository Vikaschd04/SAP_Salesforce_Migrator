"""
app.py — FastAPI backend for the H2A web dashboard.

Wraps the existing migration engine (via run_manager) and exposes it to the browser:
start a run, stream live agent events (SSE), browse the generated Salesforce project,
read reports, and download the deployable package. The extension and CLI keep using
the same engine unchanged — this is just a second front door.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import markdown as md
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, PlainTextResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from run_manager import (start_run, get_run, get_run_record, list_runs, owns,
                         queue_state, ENGINE_ROOT)
import auth
import keyvault

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"        # built React cockpit
LEGACY_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"     # no-build fallback
FRONTEND_DIR = WEB_DIST if WEB_DIST.exists() else LEGACY_FRONTEND
REPO_ROOT = ENGINE_ROOT.parent
UPLOAD_ROOT = Path(tempfile.gettempdir()) / "h2a_web_uploads"
OUTPUT_ROOT = Path(tempfile.gettempdir()) / "h2a_web_outputs"
STATE_ROOT = Path(tempfile.gettempdir()) / "h2a_web_state"     # incremental state per codebase
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
STATE_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="H2A Migration Dashboard", version="0.1.0")

# ── authentication ────────────────────────────────────────────────────────────
# Enforced in middleware rather than per-route on purpose: a route added later is
# protected by default. Opting a path OUT is a visible, deliberate edit; forgetting a
# decorator would silently expose someone's uploaded source code.

_PUBLIC = ("/api/health", "/api/config", "/api/auth/login", "/api/auth/signup",
           "/api/auth/me", "/api/auth/logout", "/api/auth/demo")
_RUN_PATH = re.compile(r"^/api/runs/([^/]+)")


def _current_user(request) -> dict | None:
    return auth.user_for_token(request.cookies.get(auth.SESSION_COOKIE))


@app.middleware("http")
async def _guard(request, call_next):
    path = request.url.path
    request.state.user = _current_user(request)

    if not auth.auth_required() or not path.startswith("/api/") or path in _PUBLIC:
        return await call_next(request)

    user = request.state.user
    if user is None:
        return JSONResponse({"detail": "Sign in to continue."}, status_code=401)

    # A valid session for the wrong tenant must not read another tenant's migration.
    m = _RUN_PATH.match(path)
    if m and not owns(m.group(1), user["id"]):
        return JSONResponse({"detail": "Not found."}, status_code=404)
    return await call_next(request)


def _set_session(resp, token: str):
    resp.set_cookie(
        auth.SESSION_COOKIE, token, httponly=True, samesite="lax",
        # Secure only off-localhost: forcing it in local dev would silently drop the
        # cookie over plain http and make login look broken.
        secure=os.environ.get("H2A_HOSTED") == "1",
        max_age=auth.SESSION_TTL, path="/")
    return resp


@app.post("/api/auth/signup")
async def api_signup(body: dict):
    if not auth.signup_open():
        raise HTTPException(403, "Registration is closed on this instance.")
    try:
        user = auth.create_user(body.get("email", ""), body.get("password", ""),
                                body.get("name", ""))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    return _set_session(JSONResponse({"user": user}), auth.create_session(user["id"]))


@app.post("/api/auth/login")
async def api_login(body: dict):
    try:
        user = auth.verify_user(body.get("email", ""), body.get("password", ""))
    except auth.AuthError as e:
        raise HTTPException(401, str(e))
    return _set_session(JSONResponse({"user": user}), auth.create_session(user["id"]))


@app.post("/api/auth/logout")
async def api_logout(request: Request):
    auth.destroy_session(request.cookies.get(auth.SESSION_COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.SESSION_COOKIE, path="/")
    return resp


# ── provider credentials ──────────────────────────────────────────────────────

@app.get("/api/keys")
async def api_keys(request: Request):
    """What this tenant has stored. Masked hints only — plaintext never leaves here."""
    user = getattr(request.state, "user", None)
    return {"available": keyvault.available(), "reason": keyvault.why_unavailable(),
            "server": keyvault.server_fallbacks(),
            "keys": keyvault.list_keys(user["id"]) if user else []}


@app.put("/api/keys/{provider}")
async def api_set_key(provider: str, body: dict, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Sign in to store a key.")
    if provider not in ("anthropic", "openrouter"):
        raise HTTPException(400, "Unknown provider.")
    try:
        return keyvault.set_key(user["id"], provider, body.get("key", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, f"Key storage is unavailable — {e}.")


@app.delete("/api/keys/{provider}")
async def api_delete_key(provider: str, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Sign in first.")
    keyvault.delete_key(user["id"], provider)
    return {"ok": True}


@app.post("/api/auth/demo")
async def api_demo_login():
    """One-click sign-in to a shared demo account, when a deployment enables it."""
    try:
        user = auth.ensure_demo_user()
    except auth.AuthError as e:
        raise HTTPException(403, str(e))
    return _set_session(JSONResponse({"user": user}), auth.create_session(user["id"]))


@app.get("/api/auth/me")
async def api_me(request: Request):
    return {"required": auth.auth_required(), "signup_open": auth.signup_open(),
            "has_users": auth.user_count() > 0, "demo": auth.demo_enabled(),
            "user": _current_user(request)}

# Report files at the output root that the dashboard surfaces.
_REPORT_FILES = ["MIGRATION_PLAN.md", "BUSINESS_RULES.md", "CHARACTERIZATION.md",
                 "FEASIBILITY_REPORT.md", "ANTI_PATTERNS.md", "TRIAGE.md", "PROVENANCE.md", "ORG_FIT.md", "PARITY.md", "DATA_MIGRATION.md",
                 "CRON_JOBS.md", "MAPPING.md"]


# ── starting a run ────────────────────────────────────────────────────────────

@app.post("/api/runs")
async def create_run(
    request: Request,
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

    # Refuse before creating a run at all, so a wrong upload is an error message rather
    # than a migration that walks you through three gates to say it found nothing.
    from src.preflight import inspect as preflight_inspect
    report = preflight_inspect(input_dir)
    if report["verdict"] == "reject":
        raise HTTPException(422, {"message": report["summary"], "preflight": report})

    user = getattr(request.state, "user", None)
    uid = (user or {}).get("id")
    run = start_run(input_dir, str(OUTPUT_ROOT / _new_out_name(input_dir)),
                    provider=provider, engine=engine, verify=verify, supervised=supervised,
                    state_dir=_state_dir_for(input_dir), owner=uid,
                    # The tenant's own credential when they have stored one; otherwise
                    # None, which falls back to the server's shared key.
                    api_key=keyvault.get_key(uid, provider))
    return {"run_id": run.id, "status": run.status, "preflight": report}


def _state_dir_for(input_dir: str) -> str:
    """Incremental state keyed by codebase, not by run: every run gets its own output
    folder (so history is preserved), but re-migrating the same repo still reuses the
    unchanged results from last time."""
    key = hashlib.md5(str(Path(input_dir).resolve()).encode("utf-8")).hexdigest()[:16]
    d = STATE_ROOT / key
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


@app.post("/api/preflight")
async def api_preflight(body: dict):
    """Inspect a codebase without starting a migration."""
    from src.preflight import inspect as preflight_inspect
    return preflight_inspect(_resolve_input_path((body.get("input_path") or "").strip()))


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


@app.post("/api/runs/{run_id}/cancel")
async def api_cancel(run_id: str):
    """Stop a run (including one abandoned at a review gate) so the engine releases the
    single-run lock and new migrations can start."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    run.request_cancel()
    return {"ok": True, "status": run.status}


HOSTED = os.environ.get("H2A_HOSTED") == "1"   # set on public deploys (Render)


def _resolve_input_path(p: str) -> str:
    path = Path(p).expanduser()
    path = (REPO_ROOT / p).resolve() if not path.is_absolute() else path.resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(400, f"Input path not found or not a directory: {path}")
    if HOSTED:
        # On a public deployment, only allow the bundled samples or uploaded zips —
        # never arbitrary server paths.
        allowed = (str(REPO_ROOT.resolve()), str(UPLOAD_ROOT.resolve()))
        if not any(str(path).startswith(a) for a in allowed):
            raise HTTPException(403, "On the hosted demo, use the sample path or upload a .zip.")
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
async def api_list_runs(request: Request):
    user = getattr(request.state, "user", None)
    return {"runs": list_runs(owner=(user or {}).get("id")), "queue": queue_state()}


@app.get("/api/runs/{run_id}")
async def api_run(run_id: str):
    run = get_run(run_id)
    if run:
        return {**run.summary(), "events": run.events}
    # Not in memory: either a run from before the last restart, or an unknown id.
    # Serving it from disk is what makes a completed migration's report outlive the
    # process that produced it.
    rec = get_run_record(run_id)
    if rec is None:
        raise HTTPException(404, "run not found")
    return rec


@app.get("/api/runs/{run_id}/stream")
async def api_stream(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")

    def gen():
        for ev in run.stream():
            if ev is None:
                # SSE comment line: per spec, invisible to EventSource/onmessage — its
                # only job is to put bytes on the wire so idle proxies/load balancers
                # (common on corporate networks) don't kill the connection while a
                # supervised run sits quiet at a review gate.
                yield ": keep-alive\n\n"
                continue
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


_REWORK_KEYWORDS = ("redo", "rework", "regenerate", "rebuild", "re-do", "re-generate",
                    "change ", "convert ", "make it", "turn it", "refactor", "fix ")


def _artifact_done_payload(a) -> dict:
    """Same shape the orchestrator emits for a finished artifact, so the frontend can
    inject it and update the feed / Artifacts / Diff exactly as during a live run."""
    return {
        "type": "artifact", "target_name": a.target_name, "layer": a.layer,
        "apex_pattern": a.apex_pattern, "status": a.status, "is_lwc": a.is_lwc,
        "findings": len(a.critic_findings),
        "findings_detail": [{"severity": f.get("severity"), "category": f.get("category"),
                             "message": f.get("message"), "suggestion": f.get("suggestion", "")}
                            for f in a.critic_findings],
        "review_flags": list(a.review_flags), "mapping_notes": (a.mapping_notes or "")[:800],
        "sobject_refs": list(a.sobject_refs or []), "business_rules": list(a.business_rules or [])[:10],
        "sources": [c.get("class_name") for c in a.source_classes],
        "lwc_parts": (sorted((a.lwc_bundle or {}).keys()) if a.is_lwc else []),
        "has_controller": bool(a.apex_controller), "reworked": True,
    }


def _detect_rework(question: str, bb):
    """If the message is an action ('redo/rework/convert X …'), return the target artifact
    + the feedback text; else None (it's a question)."""
    ql = question.lower()
    if not any(k in ql for k in _REWORK_KEYWORDS):
        return None
    for a in bb.artifacts:
        if a.target_name.lower() in ql:
            return {"target": a, "feedback": question}
    return None


def _do_regenerate(run, art, instruction: str, provider: str, who: str = "Reviewer"):
    """Re-run Builder (+Critic) on ONE artifact and update it in place.

    Safe to call while the run is paused at a review gate: the engine thread is blocked
    on the gate, so nothing else is touching this artifact. Returns None on success or
    an error string."""
    bb = run.bb
    from src.agentic.builders import BuilderAgent
    from src.agentic.critic import CriticAgent
    from src.generate import _load_mappings, write_outputs
    prev = os.environ.get("H2A_PROVIDER")
    os.environ["H2A_PROVIDER"] = provider
    try:
        BuilderAgent().rework(art, instruction, bb, [])       # scoped sigs best-effort
        findings = CriticAgent().review(art, bb.schema, offline=bb.offline)
        art.status = "accepted" if not any(f.get("severity") == "ERROR" for f in findings) else "needs_review"
        # Only write to disk when the pipeline is already finished — mid-run the
        # orchestrator writes everything at the Reconcile stage anyway.
        if run.status not in ("queued", "running"):
            write_outputs(run.output_dir, bb.generated_dicts(), bb.item_types, _load_mappings())
        bb.record(who, "regenerate", f"{art.target_name}: {instruction[:80]}")
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    finally:
        if prev is None:
            os.environ.pop("H2A_PROVIDER", None)
        else:
            os.environ["H2A_PROVIDER"] = prev


@app.post("/api/runs/{run_id}/regenerate")
async def api_regenerate(run_id: str, body: dict):
    """Regenerate a single file on demand — including while the run is paused at the
    build review gate, so a reviewer can fix one odd class without re-running anything."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    bb = getattr(run, "bb", None)
    if bb is None:
        raise HTTPException(409, "no artifacts yet for this run")
    target = (body.get("target") or "").strip()
    art = next((a for a in bb.artifacts if a.target_name == target), None)
    if art is None:
        raise HTTPException(404, f"unknown target: {target}")
    instruction = (body.get("instruction") or "").strip() or (
        "Regenerate this file. Address every Critic finding and improve correctness, "
        "security and clarity while preserving the original behavior.")
    err = _do_regenerate(run, art, instruction, (run.provider or "mock").lower())
    if err:
        raise HTTPException(500, f"regenerate failed: {err}")
    ev = _artifact_done_payload(art)
    run.emit(ev)                    # live feed / Artifacts update for anyone watching
    return {"ok": True, "artifact": ev}


def _copilot_rework(run, art, feedback: str, provider: str) -> dict:
    """Copilot action: same regeneration, phrased conversationally."""
    bb = run.bb
    err = _do_regenerate(run, art, feedback, provider, who="Copilot")
    if err:
        return {"answer": f"⚠ I couldn't rework {art.target_name}: {err}", "events": []}
    answer = (f"Done — I re-ran the Builder on **{art.target_name}** with your instruction and "
              f"re-reviewed it with the Critic (status: {art.status}, {len(art.critic_findings)} finding(s)). "
              "The Artifacts, Diff, and Files tabs now reflect the new version.")
    events = [
        {"type": "decision", "agent": "Copilot", "action": "rework", "detail": f"{art.target_name}: {feedback[:80]}"},
        _artifact_done_payload(art),
    ]
    return {"answer": answer, "events": events, "provider": provider}


@app.post("/api/runs/{run_id}/copilot")
async def api_copilot(run_id: str, body: dict):
    """Migration Copilot — ask questions, or issue actions ('redo X as a Selector')."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    question = (body.get("message") or "").strip()
    if not question:
        raise HTTPException(400, "empty message")
    # Answer with the SAME provider the run used (not the global config default) —
    # after a run finishes H2A_PROVIDER is cleared, so we key off run.provider.
    provider = (run.provider or "mock").lower()
    # 1. Action? Rework a specific target on command (works in mock + real).
    bb = getattr(run, "bb", None)
    if bb is not None:
        action = _detect_rework(question, bb)
        if action:
            return _copilot_rework(run, action["target"], action["feedback"], provider)
    # 2. Otherwise answer the question.
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


@app.get("/api/config")
async def client_config():
    """UI-facing config: on a hosted deploy the frontend hides the server-path input and
    offers upload-only, and defaults the provider to what the server is set to."""
    return {"hosted": HOSTED, "default_provider": os.environ.get("H2A_PROVIDER", "mock")}


# ── serve the dashboard ───────────────────────────────────────────────────────
def _serve_dir() -> Path:
    """Resolved on EACH request (not once at startup) so building web/dist after the
    server is already running is picked up without a restart, and it never gets stuck
    serving the old/legacy UI."""
    return WEB_DIST if WEB_DIST.exists() else LEGACY_FRONTEND


@app.get("/{full_path:path}")
async def spa(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("api"):
        raise HTTPException(404, "unknown api route")
    root = _serve_dir().resolve()
    if full_path:
        target = (root / full_path).resolve()
        if str(target).startswith(str(root)) and target.is_file():
            # content-hashed assets can be cached hard; anything else must revalidate
            cache = ("public, max-age=31536000, immutable"
                     if full_path.startswith("assets/") else "no-cache")
            return FileResponse(target, headers={"Cache-Control": cache})
    index = root / "index.html"
    if index.is_file():
        # never cache index.html → a fresh `npm run build` shows up on the next reload
        return FileResponse(index, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    raise HTTPException(404, "frontend not built — run: cd h2a-web/web && npm run build")


_boot = _serve_dir()
print(f"[h2a-web] serving frontend from {_boot} "
      f"({'React cockpit' if _boot == WEB_DIST else 'legacy fallback — web/dist missing, run npm run build'})")
