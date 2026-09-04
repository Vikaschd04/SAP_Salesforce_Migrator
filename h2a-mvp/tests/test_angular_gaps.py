"""Angular constructs that do not survive the crossing to LWC. [1.24, D1-D4]

The generator's system prompt used to carry one blanket rule:

    RxJS Observable/subscribe -> reactive property / @wire

`@wire` cannot be driven by a timer and two wires cannot be combined into a third, so for
a polling component that instruction produces something that compiles, deploys, renders
once, and never updates — with nothing in the output saying so. The same shape as the
`TRANSACTIONAL` rule removed in 1.21c: one mapping offered for a construct that has
several, and the common case getting the wrong one.

The storefront was also outside the radar entirely, which scanned `.java` and nothing
else. A component rendering money through a `currency` pipe produced a clean report.
"""

from pathlib import Path

import pytest

from src.adapters.angular_gaps import analyse, findings, grounding_for

APP = (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"
       / "js-storefront" / "acmestorefront" / "src" / "app")
TRACKER = APP / "fulfilment" / "fulfilment-tracker.component.ts"
PRICING = APP / "pricing" / "pricing-breakdown.component.ts"
PRICING_HTML = APP / "pricing" / "pricing-breakdown.component.html"


def _kinds(gaps, kind):
    return [g["construct"] for g in gaps if g["kind"] == kind]


# ── cancellation, teardown, composition ───────────────────────────────────────

def test_a_polling_component_is_found():
    """`interval` is the case the old rule got wrong: `@wire` cannot poll at all."""
    gaps = analyse(TRACKER.read_text())
    assert "interval" in _kinds(gaps, "rxjs")
    assert "switchMap" in _kinds(gaps, "rxjs")


def test_the_poll_says_the_timer_must_be_torn_down():
    """In LWC a component is destroyed on every navigation, and a surviving setInterval
    keeps calling Apex for the rest of the session."""
    fix = next(g for g in analyse(TRACKER.read_text()) if g["construct"] == "interval")["fix"]
    assert "disconnectedCallback" in fix and "clearInterval" in fix


def test_switch_map_is_described_as_cancellation_not_mapping():
    hit = next(g for g in analyse(TRACKER.read_text()) if g["construct"] == "switchMap")
    assert "cancel" in hit["hazard"]
    assert "sequence token" in hit["fix"], "the only way to express it without cancellation"
    assert hit["severity"] == "high"


def test_combine_latest_says_wire_does_not_compose():
    gaps = analyse("x = combineLatest([a$, b$]).subscribe();")
    assert gaps[0]["hazard"].count("not composable") == 1
    assert "one Apex method returning the combined shape" in gaps[0]["fix"]


def test_catch_error_is_a_fallback_not_an_error():
    """`catchError(() => of(null))` substitutes a value and the stream continues. Read as
    an error path, the component shows a banner where Angular showed data."""
    hit = next(g for g in analyse(PRICING.read_text()) if g["construct"] == "catchError")
    assert "is not an error path" in hit["hazard"]


def test_debounce_is_treated_as_load_bearing():
    """Dropped, the component still works and quietly multiplies its callout count."""
    hit = analyse("this.q.pipe(debounceTime(300)).subscribe();")[0]
    assert hit["severity"] == "high"
    assert "clearTimeout" in hit["fix"]


@pytest.mark.parametrize("op", ["mergeMap", "concatMap", "exhaustMap", "forkJoin",
                                "withLatestFrom", "shareReplay", "retry"])
def test_every_catalogued_operator_carries_a_fix(op):
    hit = analyse(f"a.pipe({op}(x));")[0]
    assert hit["fix"] and hit["hazard"]


def test_set_interval_is_not_mistaken_for_the_rxjs_operator():
    """`setInterval(` contains `Interval(` — a sloppy pattern would flag JS that is
    already correct LWC."""
    assert analyse("this._t = setInterval(() => this.load(), 15000);") == []


# ── the template ──────────────────────────────────────────────────────────────

def test_the_async_pipe_has_no_equivalent():
    hit = next(g for g in analyse("", "<p>{{ x$ | async }}</p>") if g["construct"] == "async")
    assert hit["severity"] == "high"
    assert "no async pipe" in hit["hazard"]


def test_currency_says_a_getter_still_renders_wrongly():
    """The generator's standing advice — lift it into a getter — is right for expressions
    and quietly wrong here: the raw number renders, just formatted wrong."""
    hit = analyse("", "<dd>{{ b.total | currency }}</dd>")[0]
    assert "1234.5" in hit["hazard"] and "$1,234.50" in hit["hazard"]
    assert "lightning-formatted-number" in hit["fix"]


def test_percent_warns_about_the_factor_of_a_hundred():
    hit = analyse("", "{{ r | percent }}")[0]
    assert "factor of 100" in hit["hazard"]


def test_a_named_else_branch_is_found():
    gaps = analyse("", '<div *ngIf="b$ | async as b; else loading"></div>')
    assert "loading" in _kinds(gaps, "control-flow")


def test_two_way_binding_fails_silently():
    """D1 — the field renders, accepts typing, and never updates the property."""
    hit = analyse("", '<input [(ngModel)]="code" />')[0]
    assert hit["kind"] == "binding"
    assert "never updates" in hit["hazard"]


# ── content projection and runtime instantiation ──────────────────────────────

def test_a_selector_slot_cannot_be_expressed():
    """D3 — LWC slots match a `slot` attribute, never a CSS selector."""
    hit = analyse("", '<ng-content select=".acme-header"></ng-content>')[0]
    assert hit["kind"] == "slot" and hit["severity"] == "high"
    assert "renders empty" in hit["hazard"]


def test_the_slot_fix_names_the_consumers_as_work():
    """The consumers change too, which is what makes this more than a rename."""
    fix = analyse("", '<ng-content select=".x"></ng-content>')[0]["fix"]
    assert "every consumer" in fix and "find them before" in fix


def test_a_plain_ng_content_is_not_a_gap():
    """`<ng-content>` maps to `<slot>` cleanly. Flagging it would be noise."""
    assert analyse("", "<ng-content></ng-content>") == []


@pytest.mark.parametrize("token", ["cmsComponents", "ComponentFactoryResolver",
                                   "createComponent", "ViewContainerRef"])
def test_runtime_instantiation_is_found(token):
    """D4 — LWC has no general runtime instantiation."""
    hit = analyse(f"const x = {token}(a);")[0]
    assert hit["kind"] == "cms" and hit["severity"] == "high"


def test_the_cms_answer_admits_the_design_has_to_change():
    """`lwc:is` still needs a statically imported constructor, so the set of components is
    fixed at build time — the opposite of what a CMS is for."""
    hit = analyse("provideConfig({ cmsComponents: {} })")[0]
    assert "fixed when the bundle is built" in hit["hazard"]
    assert "the design has to change" in hit["fix"]


# ── a lifecycle hook called by hand ───────────────────────────────────────────

def test_calling_ng_on_init_by_hand_is_flagged():
    """Legal in Angular, a defect in LWC — and the corpus does it."""
    hit = next(g for g in analyse(PRICING.read_text()) if g["kind"] == "lifecycle")
    assert hit["construct"] == "ngOnInit"
    assert "re-registers" in hit["hazard"]


# ── how it is reported ────────────────────────────────────────────────────────

def test_a_template_finding_is_attributed_to_the_template():
    """Reported against the `.ts`, the line number points at whatever happens to be
    on that line of a different file."""
    rows = findings(PRICING.read_text(), PRICING_HTML.read_text(),
                    "pricing.component.ts", "pricing", "pricing.component.html")
    pipes = [r for r in rows if r["rule"] == "NG_PIPE"]
    assert pipes and all(r["file"] == "pricing.component.html" for r in pipes)
    assert all(r["file"] == "pricing.component.ts"
               for r in rows if r["rule"] in ("NG_RXJS", "NG_LIFECYCLE"))


def test_repeats_of_one_construct_collapse_into_one_row():
    """Six `currency` pipes are one decision and one fix; six rows bury the rest."""
    rows = findings("", "{{a|currency}}\n{{b|currency}}\n{{c|currency}}", "x.ts", "x", "x.html")
    assert len(rows) == 1
    assert "Found 3 times" in rows[0]["hazard"]


def test_a_single_occurrence_says_nothing_about_counts():
    rows = findings("", "{{a|currency}}", "x.ts", "x", "x.html")
    assert "Found" not in rows[0]["hazard"]


def test_a_clean_component_produces_nothing():
    assert analyse("export class A {}", "<div>hi</div>") == []
    assert findings("export class A {}", "<div>hi</div>", "a.ts", "A") == []


# ── what the generator is told ────────────────────────────────────────────────

def test_the_generator_is_told_wire_is_not_the_answer():
    """The instruction being corrected is in the system prompt, so the grounding has to
    contradict it explicitly rather than merely omit it."""
    block = grounding_for({"source": TRACKER.read_text()})
    assert "`@wire` is **not** the answer" in block
    assert "cannot be driven by a timer" in block


def test_the_grounding_names_each_construct_and_its_shape():
    block = grounding_for({"source": TRACKER.read_text()})
    assert "`interval`" in block and "`switchMap`" in block
    assert "sequence token" in block


def test_the_grounding_covers_the_template_too():
    block = grounding_for({"source": PRICING.read_text(),
                           "template": PRICING_HTML.read_text()})
    assert "`currency`" in block and "`async`" in block


def test_each_construct_appears_once_in_the_grounding():
    block = grounding_for({"source": "", "template": "{{a|currency}}\n{{b|currency}}"})
    assert block.count("**`currency`**") == 1


def test_a_component_with_nothing_to_say_grounds_nothing():
    assert grounding_for({"source": "export class A {}", "template": "<p>x</p>"}) == ""
    assert grounding_for({}) == ""


# ── the radar ─────────────────────────────────────────────────────────────────

def test_the_storefront_is_in_the_radar_now():
    """It scanned `.java` and nothing else, so a component that polls produced a clean
    report and a component that silently never updates."""
    from src.radar import scan

    ng = [f for f in scan(str(APP.parents[3]))["findings"] if f["rule"].startswith("NG_")]
    assert {f["rule"] for f in ng} >= {"NG_RXJS", "NG_PIPE", "NG_LIFECYCLE"}
    assert any(f["file"].endswith(".html") for f in ng)


def test_every_frontend_rule_has_a_title():
    """An untitled rule prints its raw identifier in the report."""
    from src.radar import _RULE_TITLES, rule_title

    for rule in ("NG_RXJS", "NG_PIPE", "NG_SLOT", "NG_CMS", "NG_BINDING",
                 "NG_CONTROL_FLOW", "NG_LIFECYCLE"):
        assert rule in _RULE_TITLES, rule
        assert rule_title(rule) != rule
