#!/usr/bin/env python
"""Render docs/architecture-diagram.png — the H2A layered architecture, one image.

Palette and type match build_deck.py so the image drops into the deck (and any doc)
without looking foreign. Hue carries meaning and is used consistently everywhere:

    blue   = delivery surfaces        green  = the shared engine
    purple = LLM / provider layer     copper = human review gates

Regenerate with:  python docs/build_arch_image.py
"""
from PIL import Image, ImageDraw, ImageFont

# ── palette (build_deck.py's, plus a purple for the model layer) ──
WHITE = (255, 255, 255)
BLACK = (0x0E, 0x0E, 0x0E)
INK = (0x22, 0x24, 0x27)
GRAY = (0x53, 0x56, 0x5A)
FAINT = (0x8F, 0x92, 0x96)
LINE = (0xD2, 0xD2, 0xCF)
PANEL = (0xF7, 0xF7, 0xF5)
GREEN = (0x86, 0xBC, 0x25)
GDEEP = (0x04, 0x6A, 0x38)
BLUE = (0x00, 0x7C, 0xB0)
COPPER = (0xA9, 0x62, 0x2F)
PURPLE = (0x6B, 0x4F, 0xA8)

F = "/System/Library/Fonts/Supplemental/"


def font(name, size):
    return ImageFont.truetype(F + name, size)


SANS = lambda s: font("Arial.ttf", s)
BOLD = lambda s: font("Arial Bold.ttf", s)
MONO = lambda s: font("Courier New.ttf", s)
MONOB = lambda s: font("Courier New Bold.ttf", s)

W, H = 2600, 2400          # generous; cropped to the real content height at the end
img = Image.new("RGB", (W, H), WHITE)
d = ImageDraw.Draw(img)


def tint(c, a):
    """Blend a colour toward white — fills stay light enough for text to sit on."""
    return tuple(int(c[i] * a + 255 * (1 - a)) for i in range(3))


def box(x, y, w, h, fill=None, outline=LINE, width=2, r=10):
    d.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=fill, outline=outline, width=width)


def text(x, y, s, f, c=INK, anchor="la"):
    d.text((x, y), s, font=f, fill=c, anchor=anchor)


def wrap(s, f, maxw):
    words, lines, cur = s.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=f) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def arrow_down(x, y0, y1, c=FAINT):
    d.line([x, y0, x, y1 - 14], fill=c, width=3)
    d.polygon([(x - 11, y1 - 15), (x + 11, y1 - 15), (x, y1)], fill=c)


# ── geometry ──
M = 56
RAIL = 300                       # input / output rails
GAP = 34
SX = M + RAIL + GAP              # stack left edge
SW = W - 2 * (M + RAIL + GAP)    # stack width

# ══ title ══
text(M, 58, "H2A — Application Architecture", BOLD(56), BLACK)
text(M, 132, "SAP Hybris (Java · items.xml · Spartacus) → Salesforce (Apex · LWC · metadata)",
     SANS(27), GRAY)
d.rectangle([M, 190, M + 132, 197], fill=GREEN)

LEG = [("Delivery surface", BLUE), ("Shared engine", GDEEP), ("LLM layer", PURPLE),
       ("Human gate", COPPER)]
lx = W - M
for label, col in reversed(LEG):
    tw = d.textlength(label, font=SANS(21))
    text(lx, 78, label, SANS(21), GRAY, anchor="ra")
    d.ellipse([lx - tw - 32, 78, lx - tw - 14, 96], fill=col)
    lx -= tw + 60

TOP = 246


# ══ bands ══
HEAD_H, PAD, CGAP = 86, 22, 16   # tag strip · bottom padding · gap between cells


def band(y, tag, note, accent, cells, cols=3, tag_bg=None):
    """One horizontal layer of the stack. Sizes itself to its own content — hardcoding
    heights is how text ends up spilling out of its box. Returns the height drawn."""
    cw = (SW - 52 - (cols - 1) * CGAP) / cols
    wrapped = [wrap(desc, SANS(19), cw - 40) for _, desc, _ in cells]
    ch = 50 + max(len(w) for w in wrapped) * 26 + 14
    rows = -(-len(cells) // cols)
    h = HEAD_H + rows * (ch + CGAP) - CGAP + PAD

    box(SX, y, SW, h, fill=WHITE, outline=LINE, width=2)
    d.rounded_rectangle([SX, y, SX + SW, y + 8], radius=4, fill=accent)

    tw = d.textlength(tag, font=MONOB(21))
    d.rounded_rectangle([SX + 26, y + 26, SX + 26 + tw + 30, y + 26 + 38], radius=6,
                        fill=tint(tag_bg or accent, 0.16))
    text(SX + 41, y + 34, tag, MONOB(21), accent)
    text(SX + 26 + tw + 52, y + 36, note, SANS(21), FAINT)

    for i, ((name, _, col), lines) in enumerate(zip(cells, wrapped)):
        r, c = divmod(i, cols)
        cx, yy = SX + 26 + c * (cw + CGAP), y + HEAD_H + r * (ch + CGAP)
        box(cx, yy, cw, ch, fill=PANEL, outline=LINE, width=1, r=8)
        d.rounded_rectangle([cx, yy, cx + 5, yy + ch], radius=2, fill=col or accent)
        text(cx + 20, yy + 15, name, MONOB(22), INK)
        for j, ln in enumerate(lines):
            text(cx + 20, yy + 50 + j * 26, ln, SANS(19), GRAY)
    return h


def conn(y0, label, h=74):
    arrow_down(SX + SW / 2, y0, y0 + h)
    tw = d.textlength(label, font=MONO(20))
    d.rectangle([SX + SW / 2 - tw / 2 - 14, y0 + h / 2 - 17,
                 SX + SW / 2 + tw / 2 + 14, y0 + h / 2 + 17], fill=WHITE)
    text(SX + SW / 2, y0 + h / 2, label, MONO(20), GRAY, anchor="mm")
    return h


y = TOP
y += band(y, "LAYER 1 · SURFACES", "three clients, one engine", BLUE, [
    ("CLI", "python -m src.main agent-migrate — direct in-process call", BLUE),
    ("VS Code extension", "TypeScript webview; spawns the CLI as a child process", BLUE),
    ("Web cockpit", "React SPA + FastAPI; imports the engine on a worker thread", BLUE),
])
y += conn(y, "run_agentic_migration(input, output, *, on_event, gate, "
             "should_cancel, on_blackboard, state_dir)")

y += band(y, "LAYER 2 · ORCHESTRATION", "agentic/orchestrator.py — the only stateful coordinator",
          GDEEP, [
              ("Stage machine", "Six stages, each emitting start / done with a detail line", GDEEP),
              ("Wavefronts", "Dependency levels that can safely run in parallel", GDEEP),
              ("Human gates", "Blocks the worker thread until a verdict arrives", COPPER),
              ("Containment", "A failed class becomes a flagged stub, not an aborted run", GDEEP),
          ], cols=4)
y += conn(y, "reads / writes the shared Blackboard")

y += band(y, "LAYER 3 · AGENTS", "blackboard pattern — agents never call each other", GDEEP, [
    ("blackboard.py", "The shared workspace every agent reads and writes", GDEEP),
    ("planner.py", "Convert vs Skip; a native fit becomes a review flag", GDEEP),
    ("builders.py", "Builder + Verifier; Java→Apex, Angular→LWC", GDEEP),
    ("critic.py", "Adversarial review; findings carry a fix", GDEEP),
    ("retriever.py", "Lexical RAG over 8 bundled Salesforce docs", PURPLE),
    ("router.py", "Cheap tier to plan, frontier tier to build", PURPLE),
], cols=6)
y += conn(y, "capability modules — stateless functions over the Blackboard")

y += band(y, "LAYER 4 · CAPABILITIES", "independently testable; shared by both pipelines", GRAY, [
    ("ingest", "Hybris Java via javalang AST + layer classification", GRAY),
    ("frontend_ingest", "Spartacus / Angular components", GRAY),
    ("schema", "items.xml → SObject model", GRAY),
    ("comprehend", "Purpose, business rules, risks, complexity", GRAY),
    ("generate · _lwc", "Apex classes + tests; LWC bundle + controller", GRAY),
    ("validate · _lwc", "Static checks → LLM repair loop", GRAY),
    ("verify", "sf CLI dry-run deploy with self-heal", GRAY),
    ("rule_ledger", "Every rule traced source → artifact → test", GREEN),
    ("impex · cronjob", "Data records; cronjobs → Scheduled Apex", GRAY),
    ("report · pricing", "Feasibility, completeness ledger, cost", GRAY),
], cols=5, tag_bg=GRAY)
y += conn(y, "every model call funnels through one gateway")

y += band(y, "LAYER 5 · LLM GATEWAY", "llm.py — the single choke point for cost, retries, caching",
          PURPLE, [
              ("Providers", "anthropic · openrouter · mock — identical prompts", PURPLE),
              ("Resilience", "SDK retries + jittered app-level attempts on 429 / 5xx", PURPLE),
              ("Disk cache", "Atomic writes so a killed process leaves no torn entry", PURPLE),
              ("Accounting", "Per-model tokens, requests, retries, cache reads", PURPLE),
          ], cols=4)
STACK_BOTTOM = y


# ══ input / output rails ══
def rail(x, title, items, accent, note):
    """Source / target column. Content is centred against the stack rather than piled at
    the top, so the rail reads as a peer of the layers instead of a stub beside them."""
    top, h = TOP, STACK_BOTTOM - TOP
    box(x, top, RAIL, h, fill=WHITE, outline=LINE, width=2)
    d.rounded_rectangle([x, top, x + RAIL, top + 8], radius=4, fill=accent)
    text(x + 24, top + 32, title, MONOB(21), accent)

    note_lines = wrap(note, SANS(18), RAIL - 48)
    content = len(items) * 120 + 14 + len(note_lines) * 24
    yy = top + 86 + max(0, (h - 86 - PAD - content) / 2)

    for name, sub in items:
        box(x + 20, yy, RAIL - 40, 104, fill=PANEL, outline=LINE, width=1, r=8)
        text(x + 38, yy + 16, name, BOLD(22), INK)
        for j, ln in enumerate(wrap(sub, SANS(18), RAIL - 76)[:2]):
            text(x + 38, yy + 48 + j * 24, ln, SANS(18), GRAY)
        yy += 120

    for ln in note_lines:
        text(x + 24, yy + 14, ln, SANS(18), FAINT)
        yy += 24


rail(M, "SOURCE · SAP HYBRIS", [
    ("Java / Spring", "services, DAOs, facades, jobs"),
    ("items.xml", "the Hybris type system"),
    ("Spartacus", "*.component.ts + templates"),
    ("ImpEx · cronjobs", "seed data and schedules"),
], BLUE, "Parsed deterministically — no model calls before the first review gate.")

rail(W - M - RAIL, "TARGET · SALESFORCE", [
    ("force-app/classes", "Apex + test classes"),
    ("force-app/objects", "SObjects and fields"),
    ("force-app/lwc", "LWC bundles + controllers"),
    ("Evidence reports", "plan, business rules, feasibility"),
], GREEN, "BUSINESS_RULES.md measures completeness in rules preserved, not files converted.")

# flow arrows into and out of the stack
for x0, x1 in ((M + RAIL + 4, SX - 6), (SX + SW + 6, W - M - RAIL - 4)):
    ym = (TOP + STACK_BOTTOM) / 2
    d.line([x0, ym, x1 - 14, ym], fill=FAINT, width=3)
    d.polygon([(x1 - 15, ym - 11), (x1 - 15, ym + 11), (x1, ym)], fill=FAINT)

# ══ footer ══
fy = STACK_BOTTOM + 34
d.line([M, fy, W - M, fy], fill=LINE, width=2)
text(M, fy + 22, "H2A · HYBRIS TO APEX", MONOB(19), FAINT)
text(W - M, fy + 22,
     "Python 3.12 · FastAPI · React 18 + Vite · TypeScript · Anthropic / OpenRouter · Docker → Render",
     MONO(19), FAINT, anchor="ra")

out = "docs/architecture-diagram.png"
img = img.crop((0, 0, W, int(fy + 78)))     # trim the working canvas to real content
img.save(out, "PNG")
print(f"wrote {out}  ({img.width}×{img.height})")
