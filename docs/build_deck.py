#!/usr/bin/env python
"""Build the H2A Migrator 10-slide executive accelerator deck (A4 landscape PPTX)."""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ── palette (Deloitte-esque: white/black/cool gray + signature green) ──
BLACK=RGBColor(0x0E,0x0E,0x0E); INK=RGBColor(0x22,0x24,0x27); GRAY=RGBColor(0x53,0x56,0x5A)
FAINT=RGBColor(0x8f,0x92,0x96); LINE=RGBColor(0xd2,0xd2,0xcf); PANEL=RGBColor(0xf3,0xf3,0xf1)
WHITE=RGBColor(0xFF,0xFF,0xFF); GREEN=RGBColor(0x86,0xBC,0x25); GDEEP=RGBColor(0x04,0x6a,0x38)
TEAL=RGBColor(0x00,0x7c,0xb0); COPPER=RGBColor(0xa9,0x62,0x2f); RISK=RGBColor(0xb3,0x28,0x2d)
SANS="Arial"; MONO="Courier New"
N_SLIDES=10

# ── geometry (A4 landscape) ──
PW,PH = 11.69, 8.27
MX = 0.66
CW = PW-2*MX
EY_Y=0.52; TITLE_Y=0.9; RULE_Y=1.82; BODY=2.08
STRIP_Y=7.06; STRIP_H=0.78; FOOT_Y=7.98

prs=Presentation(); prs.slide_width=Inches(PW); prs.slide_height=Inches(PH)

def slide(bg=WHITE):
    s=prs.slides.add_slide(prs.slide_layouts[6])
    r=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,0,0,prs.slide_width,prs.slide_height)
    r.shadow.inherit=False; r.fill.solid(); r.fill.fore_color.rgb=bg; r.line.fill.background()
    return s

def rect(s,l,t,w,h,fill=None,ln=None,lw=0.75,shape=MSO_SHAPE.RECTANGLE):
    sp=s.shapes.add_shape(shape,Inches(l),Inches(t),Inches(w),Inches(h)); sp.shadow.inherit=False
    if fill is None: sp.fill.background()
    else: sp.fill.solid(); sp.fill.fore_color.rgb=fill
    if ln is None: sp.line.fill.background()
    else: sp.line.color.rgb=ln; sp.line.width=Pt(lw)
    return sp

def tf_box(s,l,t,w,h,anchor=MSO_ANCHOR.TOP,wrap=True):
    tb=s.shapes.add_textbox(Inches(l),Inches(t),Inches(w),Inches(h)); tf=tb.text_frame
    tf.word_wrap=wrap; tf.vertical_anchor=anchor
    tf.margin_left=0; tf.margin_right=0; tf.margin_top=0; tf.margin_bottom=0
    return tf

def _track(run,pts): run._r.get_or_add_rPr().set('spc',str(int(pts*100)))

def para(tf, runs, align=PP_ALIGN.LEFT, size=11, color=INK, bold=False, name=SANS,
         italic=False, sa=3, sb=0, line=1.08):
    p0=tf.paragraphs[0]
    p = p0 if (not p0.runs) else tf.add_paragraph()
    p.alignment=align; p.space_after=Pt(sa); p.space_before=Pt(sb); p.line_spacing=line
    if isinstance(runs,str): runs=[(runs,{})]
    for txt,st in runs:
        r=p.add_run(); r.text=txt; f=r.font
        f.size=Pt(st.get('size',size)); f.bold=st.get('bold',bold); f.italic=st.get('italic',italic)
        f.name=st.get('name',name); f.color.rgb=st.get('color',color)
        if st.get('track'): _track(r,st['track'])
    return p

def eyebrow(s,kick,dark=False):
    rect(s,MX,EY_Y+0.02,0.13,0.13,fill=GREEN,shape=MSO_SHAPE.OVAL)
    tf=tf_box(s,MX+0.27,EY_Y-0.04,CW-0.3,0.32)
    para(tf,[(kick.upper(),dict(size=10.5,bold=True,color=(FAINT if dark else GRAY),name=MONO,track=2.0))])

def title(s,lines,size=29,dark=False,y=TITLE_Y):
    ink=WHITE if dark else BLACK
    tf=tf_box(s,MX,y,CW,1.05)
    for i,ln in enumerate(lines):
        runs=[(ln,dict(size=size,bold=True,color=ink,name=SANS))]
        if i==len(lines)-1: runs.append((".",dict(size=size,bold=True,color=GREEN,name=SANS)))
        para(tf,runs,size=size,line=1.02,sa=0)

def footer(s,page,dark=False):
    col=RGBColor(0x6a,0x6d,0x70) if dark else FAINT
    tf=tf_box(s,MX,FOOT_Y,4,0.25); para(tf,[("H2A MIGRATOR · ACCELERATOR",dict(size=8,color=col,name=MONO,track=1.2))])
    tf2=tf_box(s,PW-MX-2.2,FOOT_Y,2.0,0.25); para(tf2,[(f"{page:02d} / {N_SLIDES}",dict(size=8,color=col,name=MONO,track=1.2))],align=PP_ALIGN.RIGHT)
    rect(s,PW-MX-0.14,FOOT_Y+0.025,0.09,0.09,fill=GREEN,shape=MSO_SHAPE.OVAL)

def header(s,kick,lines,page,tsize=29):
    eyebrow(s,kick); title(s,lines,size=tsize)
    rect(s,MX,RULE_Y,CW,0.02,fill=LINE)
    footer(s,page)

def card(s,l,t,w,h,top=BLACK,fill=WHITE,border=LINE):
    r=rect(s,l,t,w,h,fill=fill,ln=border,lw=0.75)
    if top: rect(s,l,t,w,0.055,fill=top)
    return r

def strip(s,label,body_runs,y=STRIP_Y,h=STRIP_H):
    rect(s,MX,y,CW,h,fill=PANEL)
    rect(s,MX,y,0.07,h,fill=GREEN)
    tf=tf_box(s,MX+0.28,y+0.12,CW-0.55,h-0.22)
    para(tf,[(label.upper(),dict(size=8.5,bold=True,color=GDEEP,name=MONO,track=1.4))],sa=4)
    para(tf,body_runs,size=11.5,color=INK,line=1.16)

def chips(s,items,y,l=MX):
    x=l
    for it in items:
        w=0.36+len(it['t'])*0.086
        rect(s,x,y,w,0.38,fill=WHITE,ln=LINE,lw=0.75)
        tf=tf_box(s,x+0.15,y,w-0.3,0.38,anchor=MSO_ANCHOR.MIDDLE,wrap=False)
        para(tf,it['runs'],size=9,name=MONO,color=GRAY,line=1.0)
        x+=w+0.2

def cols(n,gap,l=MX,w=CW):
    cw=(w-(n-1)*gap)/n
    return [l+i*(cw+gap) for i in range(n)], cw

# ══════════════════════════════════════════════════════════════════════════
# 1 · COVER
s=slide()
rect(s,7.9,0.7,4.9,4.9,ln=GREEN,lw=1.5,shape=MSO_SHAPE.OVAL)
rect(s,9.2,3.4,3.2,3.2,ln=LINE,lw=1.0,shape=MSO_SHAPE.OVAL)
rect(s,7.62,1.02,0.32,0.32,fill=GREEN,shape=MSO_SHAPE.OVAL)
eyebrow(s,"Migration Accelerator · Executive Overview")
tf=tf_box(s,MX,1.4,7.6,1.6)
para(tf,[("SAP Hybris to Salesforce.",dict(size=34,bold=True,color=BLACK))],line=1.05,sa=0)
para(tf,[("Migrated by AI. Proven to run",dict(size=34,bold=True,color=BLACK)),(".",dict(size=34,bold=True,color=GREEN))],line=1.05,sa=0)
rect(s,MX,2.85,0.95,0.08,fill=GREEN)
tf=tf_box(s,MX,3.15,7.1,1.2)
para(tf,"Migrating a complete Hybris estate is a multi-month program. This accelerator removes the biggest bottleneck — it uses AI to do the manual code-move, and then proves the result actually works, before your experts spend a minute on it.",size=13.5,color=GRAY,line=1.3)
fx=MX
for t,c,arrow in [("SAP HYBRIS · JAVA",COPPER,True),("AI AGENT TEAM",BLACK,True),("SALESFORCE · APEX",TEAL,False)]:
    w=0.3+len(t)*0.083
    rect(s,fx,4.75,w,0.42,ln=c,lw=1.5)
    tf=tf_box(s,fx,4.75,w,0.42,anchor=MSO_ANCHOR.MIDDLE,wrap=False); para(tf,[(t,dict(size=10,bold=True,color=c,name=MONO))],align=PP_ALIGN.CENTER)
    fx+=w
    if arrow:
        tf=tf_box(s,fx,4.75,0.5,0.42,anchor=MSO_ANCHOR.MIDDLE); para(tf,[("──▶",dict(size=11,color=FAINT))],align=PP_ALIGN.CENTER); fx+=0.5
chips(s,[{'t':"VS Code extension + CLI",'runs':[("VS Code extension ",{}),("+ CLI",dict(bold=True,color=BLACK))]},
         {'t':"Powered by Anthropic Claude",'runs':[("Powered by ",{}),("Anthropic Claude",dict(bold=True,color=BLACK))]},
         {'t':"63 automated tests · all passing",'runs':[("63",dict(bold=True,color=BLACK)),(" automated tests · all passing",{})]}],5.65)
footer(s,1)

# 2 · THE PROBLEM
s=slide()
header(s,"01 · The Problem",["A full Hybris migration by hand is slow, expensive —","and it quietly loses business logic"],2,tsize=25)
lx,cw=cols(3,0.32)
data=[("Months → Years","A complete Hybris estate holds hundreds of Java classes, a custom data model, live data, and scheduled jobs. Rewriting it manually is measured in quarters — often years."),
("Rare, costly experts","It needs engineers senior in both Hybris and Salesforce — one of the scarcest, most expensive skill combinations in the market."),
("Silent logic loss","Rules like “never accept a zero-value order” vanish during a manual rewrite. Nobody notices — until it breaks in production.")]
for i,(big,body) in enumerate(data):
    x=lx[i]; card(s,x,BODY+0.15,cw,3.9,top=RISK)
    tf=tf_box(s,x+0.24,BODY+0.42,cw-0.48,1.0); para(tf,[(big,dict(size=18,bold=True,color=RISK))],line=1.05)
    tf=tf_box(s,x+0.24,BODY+1.45,cw-0.48,2.3); para(tf,body,size=11,color=GRAY,line=1.28)
strip(s,"In plain words",[("Rewriting an old system by hand is like retyping a 1,000-page contract from memory — slow, and the fine print is what gets lost.",{})])

# 3 · THE ACCELERATOR
s=slide(PANEL)
header(s,"02 · The Accelerator",["Point it at the old code.","Get a verified Salesforce project back"],3,tsize=26)
boxw=4.35; gap=CW-2*boxw
card(s,MX,BODY+0.35,boxw,3.4,top=COPPER)
tf=tf_box(s,MX+0.28,BODY+0.63,boxw-0.5,0.4); para(tf,[("IN — a Hybris codebase",dict(size=13.5,bold=True,color=BLACK))])
tf=tf_box(s,MX+0.28,BODY+1.15,boxw-0.5,2.3)
for it in ["Java business logic (orders, customers, pricing…)","The data model (items.xml)","Actual data records (ImpEx files)","Scheduled jobs (cronjobs + triggers)"]:
    para(tf,[("—  ",dict(color=COPPER)),(it,dict(color=GRAY))],size=11.5,line=1.2,sa=8)
gx=MX+boxw+gap/2-0.5
rect(s,gx,BODY+1.45,1.0,1.0,fill=BLACK,shape=MSO_SHAPE.OVAL)
tf=tf_box(s,gx,BODY+1.45,1.0,1.0,anchor=MSO_ANCHOR.MIDDLE); para(tf,[("AI AGENT\nTEAM",dict(size=8,bold=True,color=WHITE,name=MONO))],align=PP_ALIGN.CENTER,line=1.2)
rect(s,gx+0.82,BODY+2.17,0.12,0.12,fill=GREEN,shape=MSO_SHAPE.OVAL)
tf=tf_box(s,gx-0.35,BODY+2.6,1.7,0.3); para(tf,[("MINUTES–HOURS",dict(size=8.5,color=FAINT,name=MONO))],align=PP_ALIGN.CENTER)
ox=MX+boxw+gap
card(s,ox,BODY+0.35,boxw,3.4,top=TEAL)
tf=tf_box(s,ox+0.28,BODY+0.63,boxw-0.5,0.4); para(tf,[("OUT — deployable Salesforce",dict(size=13.5,bold=True,color=BLACK))])
tf=tf_box(s,ox+0.28,BODY+1.15,boxw-0.5,2.3)
for it in ["Apex code in Salesforce enterprise patterns","A test class for every class","Data model, data & schedules — migrated","Confidence report: what to trust, what to review"]:
    para(tf,[("—  ",dict(color=TEAL)),(it,dict(color=GRAY))],size=11.5,line=1.2,sa=8)
strip(s,"Why it matters",[("The full migration is still a program — but the code-move stops being the bottleneck. The accelerator does the grind with AI intelligence; your experts review a scored draft instead of rewriting from scratch.",{})])

# 4 · ARCHITECTURE
s=slide()
header(s,"03 · Architecture",["Four layers, one engine"],4,tsize=30)
layers=[("INTERFACES",BLACK,["VS Code extension — right-click","Command line — for CI/CD","both drive the same engine"]),
("ORCHESTRATION",GDEEP,["Agentic mode — Planner · Builder · Critic · Verifier","Linear mode — fixed 10-stage pipeline"]),
("SHARED STAGE FUNCTIONS",BLACK,["parse Java","derive schema","generate Apex","validate & repair","data · jobs","verify · report"]),
("AI PROVIDERS",BLACK,["Anthropic Claude — best quality","OpenRouter — cheap iteration","Mock — free, offline, zero exposure"])]
ly=BODY+0.05; lh=0.86
for i,(name,lc,nodes) in enumerate(layers):
    rect(s,MX,ly,CW,lh,fill=WHITE,ln=LINE,lw=0.75)
    rect(s,MX,ly,1.95,lh,fill=lc)
    tf=tf_box(s,MX+0.16,ly,1.7,lh,anchor=MSO_ANCHOR.MIDDLE); para(tf,[(name,dict(size=8.5,bold=True,color=WHITE,name=MONO,track=0.8))],line=1.1)
    nx=MX+2.15
    for nd in nodes:
        w=0.28+len(nd)*0.066
        rect(s,nx,ly+lh/2-0.19,w,0.38,fill=PANEL,ln=LINE,lw=0.5)
        tf=tf_box(s,nx+0.1,ly+lh/2-0.19,w-0.2,0.38,anchor=MSO_ANCHOR.MIDDLE); para(tf,[(nd,dict(size=9.5,bold=True,color=BLACK))])
        nx+=w+0.14
    if i<3:
        tf=tf_box(s,MX,ly+lh-0.02,CW,0.24); para(tf,[("▼",dict(size=9,color=FAINT))],align=PP_ALIGN.CENTER)
    ly+=lh+0.24
strip(s,"In plain words",[("Two “driving modes” — a smart agent team, or a simple assembly line — share the same proven tools underneath. And the AI brain is swappable, including a free offline one for zero-exposure evaluation.",{})])

# 5 · THE AI AGENT TEAM
s=slide(PANEL)
header(s,"04 · The AI Agent Team",["A manager, a shared whiteboard, and four specialists"],5,tsize=26)
rect(s,MX,BODY+0.1,CW,0.52,fill=BLACK)
tf=tf_box(s,MX,BODY+0.1,CW,0.52,anchor=MSO_ANCHOR.MIDDLE)
para(tf,[("Orchestrator   ",dict(size=12.5,bold=True,color=WHITE)),("ROUTES WORK · LOOPS UNTIL EVERYTHING IS VERIFIED",dict(size=8.5,color=GREEN,name=MONO,track=1.0))],align=PP_ALIGN.CENTER)
tf=tf_box(s,MX,BODY+0.63,CW,0.2); para(tf,[("▲   ▼",dict(size=8.5,color=FAINT))],align=PP_ALIGN.CENTER)
rect(s,MX,BODY+0.84,CW,0.5,ln=GREEN,lw=1.5,fill=WHITE)
tf=tf_box(s,MX,BODY+0.84,CW,0.5,anchor=MSO_ANCHOR.MIDDLE)
para(tf,[("The Blackboard",dict(size=11.5,bold=True,color=GDEEP)),(" — shared state: schema · migration plan · artifacts · ",dict(size=10.5,color=INK)),("decision log",dict(size=10.5,bold=True,color=GDEEP)),(" · open questions",dict(size=10.5,color=INK))],align=PP_ALIGN.CENTER)
tf=tf_box(s,MX,BODY+1.37,CW,0.2); para(tf,[("▲   ▼",dict(size=8.5,color=FAINT))],align=PP_ALIGN.CENTER)
lx,cw=cols(4,0.24)
ag=[("STRATEGY","The Planner","Decides what becomes Apex, what should be a native Salesforce product, and what to skip — with a written rationale.","“Pricing rules? That's CPQ — don't hand-build it.”"),
("EXECUTION","The Builder","Writes the Apex + a test class per class, grounded in your real data model and best practices.","“Bulk-safe, secure, on pattern — like a senior dev.”"),
("QUALITY GATE","The Critic","Adversarially reviews every piece: is the original behavior preserved? Is it secure?","“The zero-total rule got dropped — blocked.”"),
("PROOF","The Verifier","Deploys to a real org, reads real compiler errors, and heals them until green.","“Not ‘looks right’ — it actually ran.”")]
for i,(role,nm,body,q) in enumerate(ag):
    x=lx[i]; card(s,x,BODY+1.62,cw,3.0,top=GREEN)
    tf=tf_box(s,x+0.18,BODY+1.85,cw-0.36,0.22); para(tf,[(role,dict(size=7.5,bold=True,color=GDEEP,name=MONO,track=0.8))])
    tf=tf_box(s,x+0.18,BODY+2.1,cw-0.36,0.32); para(tf,[(nm,dict(size=13.5,bold=True,color=BLACK))])
    tf=tf_box(s,x+0.18,BODY+2.5,cw-0.36,1.35); para(tf,body,size=9.8,color=GRAY,line=1.24)
    rect(s,x+0.18,BODY+3.85,0.04,0.6,fill=GREEN)
    tf=tf_box(s,x+0.3,BODY+3.85,cw-0.5,0.7); para(tf,[(q,dict(italic=True,color=INK))],size=9.2,line=1.2)
footer(s,5)

# 6 · THE PIPELINE
s=slide()
header(s,"05 · The Pipeline",["Ten stages, end to end"],6,tsize=30)
stg=[("01","Crawl & schedule","Group classes by domain; sort so dependencies convert first.",0),
("02","Call graph","Map who-calls-whom for the visual dashboard.",0),
("03","Ingest","Parse the Java and data-model definitions precisely.",0),
("04","Derive schema","Build the target object/field catalog — the source of truth.",0),
("05","Comprehend","AI summarises each class: purpose, queries, rules.",1),
("06","Generate","AI writes the Apex + tests, grounded in the schema.",1),
("07","Validate & repair","Safety checks; failures loop back to the AI to fix.",1),
("08","Reconcile & metadata","Fill schema gaps with evidence; emit objects & fields.",0),
("09","Data & jobs","ImpEx → CSVs; cron triggers → scheduling runbook.",0),
("10","Verify & report","Real-org deploy + self-heal; confidence scores.",1)]
lx,cw=cols(5,0.22); ch=1.55
for i,(n,t,b,ai) in enumerate(stg):
    x=lx[i%5]; y=BODY+0.05+(i//5)*(ch+0.24)
    card(s,x,y,cw,ch,top=None)
    tf=tf_box(s,x+0.16,y+0.14,cw-0.3,0.24); para(tf,[(n,dict(size=9,bold=True,color=GDEEP,name=MONO))])
    if ai:
        rect(s,x+cw-0.5,y+0.13,0.36,0.24,fill=BLACK)
        tf=tf_box(s,x+cw-0.5,y+0.12,0.36,0.24,anchor=MSO_ANCHOR.MIDDLE); para(tf,[("AI",dict(size=8,bold=True,color=WHITE,name=MONO))],align=PP_ALIGN.CENTER)
    tf=tf_box(s,x+0.16,y+0.4,cw-0.3,0.35); para(tf,[(t,dict(size=11,bold=True,color=BLACK))],line=1.05)
    tf=tf_box(s,x+0.16,y+0.78,cw-0.3,0.7); para(tf,b,size=8.6,color=GRAY,line=1.2)
strip(s,"In plain words",[("The ",{}),("AI",dict(bold=True,color=BLACK)),(" is used only where judgement is needed — understanding and writing code. Everything mechanical is ordinary tested software: fast, free, repeatable.",{})])

# 7 · SELF-HEALING VERIFICATION
s=slide(PANEL)
header(s,"06 · Why You Can Trust It",["It doesn't stop at “the AI wrote code.” It proves the code runs"],7,tsize=23)
lx,cw=cols(4,0.22)
loop=[("Deploy for real","Validation-only deploy to an actual Salesforce org"),
("Read real errors","The actual compiler output — not a guess"),
("Fix automatically","Three healing modes (below)"),
("Repeat until green","Anything unresolved is flagged for a human")]
for i,(t,b) in enumerate(loop):
    x=lx[i]; card(s,x,BODY+0.1,cw,1.15,top=None)
    tf=tf_box(s,x+0.16,BODY+0.28,cw-0.3,0.3); para(tf,[(t,dict(size=11.5,bold=True,color=BLACK))],align=PP_ALIGN.CENTER)
    tf=tf_box(s,x+0.16,BODY+0.62,cw-0.3,0.5); para(tf,b,size=9,color=GRAY,align=PP_ALIGN.CENTER,line=1.2)
    if i<3:
        tf=tf_box(s,x+cw,BODY+0.45,0.22,0.4,anchor=MSO_ANCHOR.MIDDLE); para(tf,[("→",dict(size=13,color=FAINT))],align=PP_ALIGN.CENTER)
tf=tf_box(s,MX,BODY+1.4,CW,0.3); para(tf,[("↺  BOUNDED LOOP — RUNS UNTIL GREEN, NEVER SILENTLY SHIPS",dict(size=9,bold=True,color=GDEEP,name=MONO,track=1.0))],align=PP_ALIGN.CENTER)
lx3,cw3=cols(3,0.3)
heal=[("Metadata healing","“Missing field” error? If the field is genuinely used in the original Java — proven by evidence — it's added to the data model. Never guessed."),
("Code repair","Compile errors are fed back to the AI with the real error message, and the class is rewritten and re-tried."),
("Coverage healing","Salesforce requires 75% test coverage to deploy. Below it? The tool writes more tests — error paths, bulk scenarios — until it clears the bar.")]
for i,(t,b) in enumerate(heal):
    x=lx3[i]; card(s,x,BODY+1.85,cw3,2.4,top=BLACK)
    tf=tf_box(s,x+0.22,BODY+2.08,cw3-0.44,0.35); para(tf,[(t,dict(size=12.5,bold=True,color=BLACK))])
    tf=tf_box(s,x+0.22,BODY+2.5,cw3-0.44,1.6); para(tf,b,size=10.3,color=GRAY,line=1.26)
strip(s,"In plain words",[("The AI can only use fields that provably exist, a second AI challenges every piece, and the code must actually compile against a real org. Correctness comes from the loop — not from trusting the model.",{})])

# 8 · WHAT YOU GET
s=slide()
header(s,"07 · The Deliverable",["What lands in the output folder"],8,tsize=30)
lx,cw=cols(3,0.3)
inv=[("force-app/…/classes","Apex code + tests","Selectors, Services, REST controllers, scheduled jobs — each with its own test class."),
("force-app/…/objects","Data model","Custom objects, fields, picklists, relationships, required/unique constraints."),
("data/ · DATA_MIGRATION.md","The data","Load-ready CSVs plus a safe, re-runnable import runbook."),
("CRON_JOBS.md · schedule.apex","Schedules","Every timed job translated, same timing, with a ready-to-run script."),
("MIGRATION_PLAN.md","The decisions","The Planner's call on every class, the Critic's findings, the full decision log."),
("FEASIBILITY_REPORT.md","The scorecard","Validation results, a High/Medium/Low confidence score per class, deploy status, cost.")]
for i,(code,t,b) in enumerate(inv):
    x=lx[i%3]; y=BODY+0.1+(i//3)*1.85
    card(s,x,y,cw,1.65,top=None)
    rect(s,x+0.2,y+0.18,min(cw-0.4,0.2+len(code)*0.062),0.3,fill=PANEL)
    tf=tf_box(s,x+0.28,y+0.18,cw-0.5,0.3,anchor=MSO_ANCHOR.MIDDLE); para(tf,[(code,dict(size=8.5,color=GDEEP,name=MONO))])
    tf=tf_box(s,x+0.2,y+0.54,cw-0.4,0.3); para(tf,[(t,dict(size=11.5,bold=True,color=BLACK))])
    tf=tf_box(s,x+0.2,y+0.88,cw-0.4,0.7); para(tf,b,size=9.5,color=GRAY,line=1.22)
chips(s,[{'t':"63 automated tests, all passing",'runs':[("63",dict(bold=True,color=BLACK)),(" automated tests, all passing",{})]},
         {'t':"3 AI providers incl. free offline",'runs':[("3",dict(bold=True,color=BLACK)),(" AI providers incl. free offline",{})]},
         {'t':"every run reports its own cost",'runs':[("every run reports its own ",{}),("cost",dict(bold=True,color=BLACK))]}],BODY+3.95)
strip(s,"In plain words",[("Not just code — a complete package: the system, its data, its schedules, and the paper trail that tells your reviewers exactly where to look.",{})])

# 9 · THE BUSINESS CASE
s=slide(PANEL)
header(s,"08 · The Business Case",["What the accelerator changes, concretely"],9,tsize=28)
ty=BODY+0.15; rh=0.72
tf=tf_box(s,MX+0.1,ty,5,0.3); para(tf,[("WITHOUT THE ACCELERATOR",dict(size=8.5,color=GRAY,name=MONO,track=1.0))])
tf=tf_box(s,MX+CW/2+0.1,ty,5,0.3); para(tf,[("WITH THE ACCELERATOR",dict(size=8.5,color=GRAY,name=MONO,track=1.0))])
rect(s,MX,ty+0.32,CW,0.022,fill=BLACK)
biz=[("Months of manual rewriting","A working, verified first draft in minutes–hours"),
("Business rules silently lost","An AI reviewer checks rule preservation; a parity score proves it"),
("“Trust me, it compiles”","Deployed to a real org and self-corrected until verifiably green"),
("Everything becomes custom code to own forever","Native Salesforce products recommended where they fit — less debt"),
("A black-box engagement","A decision log and a confidence score on every class")]
for i,(a,b) in enumerate(biz):
    y=ty+0.4+i*rh
    tf=tf_box(s,MX+0.1,y,CW/2-0.3,rh-0.12,anchor=MSO_ANCHOR.MIDDLE); para(tf,[(a,dict(size=11.5,bold=True,color=RISK))],line=1.12)
    tf=tf_box(s,MX+CW/2+0.1,y,CW/2-0.3,rh-0.12,anchor=MSO_ANCHOR.MIDDLE); para(tf,[(b,dict(size=11.5,bold=True,color=GDEEP))],line=1.12)
    rect(s,MX,y+rh-0.06,CW,0.012,fill=LINE)
strip(s,"The honest positioning",[("A strong, verified first draft plus a prioritized review list. It makes expert reviewers dramatically faster — it doesn't remove them, and we don't pretend it does.",{})])

# 10 · CLOSE
s=slide(BLACK)
rect(s,4.6,6.7,2.5,2.5,ln=RGBColor(0x2a,0x2a,0x2a),lw=1.0,shape=MSO_SHAPE.OVAL)
tf=tf_box(s,0,1.7,PW,0.4); para(tf,[("● THE ASK",dict(size=10,bold=True,color=GREEN,name=MONO,track=2.0))],align=PP_ALIGN.CENTER)
tf=tf_box(s,1.0,2.5,PW-2,1.6)
para(tf,[("Give us one real slice of a Hybris codebase.",dict(size=27,bold=True,color=WHITE))],align=PP_ALIGN.CENTER,line=1.12,sa=4)
para(tf,[("We'll hand back verified Salesforce — and the receipts",dict(size=27,bold=True,color=WHITE)),(" ●",dict(size=27,bold=True,color=GREEN))],align=PP_ALIGN.CENTER,line=1.12)
tf=tf_box(s,2.2,4.5,PW-4.4,0.9); para(tf,"A pilot costs days, not months. Free mock mode first, a scored real run second, your team's verdict third.",size=13,color=RGBColor(0xa7,0xa8,0xaa),align=PP_ALIGN.CENTER,line=1.3)
citems=[("Live demo today",[("Live demo ",dict(color=RGBColor(0xa7,0xa8,0xaa))),("today",dict(bold=True,color=WHITE))]),
("Full docs: PRD · TDD · flows · security",[("Full docs: ",dict(color=RGBColor(0xa7,0xa8,0xaa))),("PRD · TDD · flows · security",dict(bold=True,color=WHITE))]),
("Pilot-ready",[("Pilot-ready",dict(bold=True,color=WHITE))])]
cw_c=[0.42+len(t)*0.088 for t,_ in citems]
tot=sum(cw_c)+0.4
cx=(PW-tot)/2
for (t,runs),w in zip(citems,cw_c):
    rect(s,cx,5.6,w,0.42,fill=RGBColor(0x18,0x18,0x18),ln=RGBColor(0x3a,0x3a,0x3a),lw=0.75)
    tf=tf_box(s,cx+0.18,5.6,w-0.36,0.42,anchor=MSO_ANCHOR.MIDDLE,wrap=False); para(tf,runs,size=9,name=MONO,align=PP_ALIGN.CENTER)
    cx+=w+0.2
footer(s,10,dark=True)

import sys
out=sys.argv[1] if len(sys.argv)>1 else "DEMO_DECK.pptx"
prs.save(out)
print("saved",out,"slides:",len(prs.slides._sldIdLst))
