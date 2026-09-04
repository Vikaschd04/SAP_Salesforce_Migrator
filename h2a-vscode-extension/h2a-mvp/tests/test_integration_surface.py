"""The integration surface: REST endpoints, guest callers, and upsert keys. [1.25, E1-E3]

Spring resolves any number of endpoints at any path shape. Apex REST allows one method per
verb per class and a `urlMapping` of one literal prefix plus one trailing `*`. A controller
can therefore be untranslatable in two ways that look nothing alike from the output: the
class does not compile, or it compiles and the endpoint never matches.

E3 is the quieter one. `INSERT_UPDATE` is an upsert and an upsert needs a key the target
enforces. `mark_external_id_fields` skips a missing field by design — correct for a
data-only run — and the runbook still prints a confident load command for it.
"""

from pathlib import Path

import pytest

from src.adapters.rest_surface import (HEAP_SYNC_MB, VERB_LIMIT, endpoints, findings,
                                       grounding_for)

CONTROLLER = (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"
              / "core-customize/hybris/bin/custom/acmeoccaddon/web/src/com/acme/occ"
              / "controllers" / "PricingController.java")


def _rules(rows):
    return {r["rule"] for r in rows}


def _one(rows, rule):
    return next(r for r in rows if r["rule"] == rule)


# ── reading the controller ────────────────────────────────────────────────────

def test_both_endpoints_are_found_with_the_class_prefix_applied():
    eps = endpoints(CONTROLLER.read_text())
    assert [e["method"] for e in eps] == ["getBreakdown", "quote"]
    assert eps[0]["full_path"] == "/{baseSiteId}/pricing/orders/{code}/breakdown"
    assert eps[1]["full_path"] == "/{baseSiteId}/pricing/quote"


def test_the_class_level_mapping_is_not_itself_an_endpoint():
    assert all(e["method"] != "(unnamed)" for e in endpoints(CONTROLLER.read_text()))


def test_a_plain_class_is_not_a_controller():
    assert endpoints("public class Helper { void f() {} }") == []


@pytest.mark.parametrize("ann,verb", [("@GetMapping(\"/a\")", "GET"),
                                      ("@PostMapping(\"/a\")", "POST"),
                                      ("@PutMapping(\"/a\")", "PUT"),
                                      ("@DeleteMapping(\"/a\")", "DELETE"),
                                      ("@PatchMapping(\"/a\")", "PATCH")])
def test_the_shorthand_annotations_carry_their_verb(ann, verb):
    src = f"@RestController public class C {{ {ann} public String f() {{ return null; }} }}"
    assert endpoints(src)[0]["verb"] == verb


# ── one method per verb ───────────────────────────────────────────────────────

def test_two_gets_in_one_class_is_reported():
    """An Apex `@RestResource` class may declare one `@HttpGet`. Emitted as written the
    class does not compile, and the error names the duplicate annotation rather than the
    design problem behind it."""
    row = _one(findings(CONTROLLER.read_text(), "x.java", "PricingController"),
               "REST_VERB_COLLISION")
    assert row["severity"] == "high"
    assert "`getBreakdown()`" in row["hazard"] and "`quote()`" in row["hazard"]


def test_the_fix_forbids_merging_the_two_endpoints():
    """The cheap way out — one method doing both — silently changes what callers get."""
    row = _one(findings(CONTROLLER.read_text(), "x.java", "PricingController"),
               "REST_VERB_COLLISION")
    assert "they return different" in row["fix"]


def test_one_endpoint_per_verb_is_not_reported():
    src = ('@RestController @RequestMapping("/p") public class C {'
           ' @GetMapping("/a") public String f() { return null; }'
           ' @PostMapping("/b") public String g() { return null; } }')
    assert "REST_VERB_COLLISION" not in _rules(findings(src, "x.java", "C"))
    assert VERB_LIMIT == 1


# ── paths urlMapping cannot express ───────────────────────────────────────────

def test_a_mid_path_variable_is_reported():
    rows = [r for r in findings(CONTROLLER.read_text(), "x.java", "PricingController")
            if r["rule"] == "REST_PATH_TEMPLATE"]
    assert len(rows) == 2, "both endpoints start with {baseSiteId}"
    assert "never matches" in rows[0]["hazard"]


def test_a_trailing_variable_is_expressible_and_not_reported():
    """`/orders/{code}` is exactly what a trailing wildcard covers."""
    src = ('@RestController @RequestMapping("/orders") public class C {'
           ' @GetMapping("/{code}") public String f() { return null; } }')
    assert "REST_PATH_TEMPLATE" not in _rules(findings(src, "x.java", "C"))


def test_a_fixed_path_is_not_reported():
    src = ('@RestController @RequestMapping("/orders") public class C {'
           ' @GetMapping("/recent") public String f() { return null; } }')
    assert "REST_PATH_TEMPLATE" not in _rules(findings(src, "x.java", "C"))


def test_the_suggested_mapping_is_not_a_double_slash():
    """`full_path.split("{")[0]` on `/{baseSiteId}/pricing` yields `/`, and the advice
    would read `urlMapping='//*'`. OCC paths begin with a variable segment routinely."""
    row = [r for r in findings(CONTROLLER.read_text(), "x.java", "C")
           if r["rule"] == "REST_PATH_TEMPLATE"][0]
    assert "//*" not in row["fix"]
    assert "urlMapping='/pricing/*'" in row["fix"]


def test_a_leading_site_variable_is_explained_as_a_url_change():
    """A base-site id is not a path segment on the target, so every caller's URL changes —
    which is a migration task, not a mapping detail."""
    row = [r for r in findings(CONTROLLER.read_text(), "x.java", "C")
           if r["rule"] == "REST_PATH_TEMPLATE"][0]
    assert "every caller's URL changes" in row["fix"]


# ── callers with no session ───────────────────────────────────────────────────

def test_a_payment_callback_is_flagged_for_guest_access():
    src = ('@RestController @RequestMapping("/psp") public class PaymentCallbackController {'
           ' @PostMapping("/callback") public String f() { return null; } }')
    row = _one(findings(src, "x.java", "PaymentCallbackController"), "REST_GUEST_ACCESS")
    assert row["severity"] == "high"
    assert "401" in row["hazard"] and "403" in row["hazard"]


def test_the_guest_fix_lists_every_prerequisite_and_how_to_prove_it():
    """Each of Site, guest profile and CORS fails the same way, so a signed-in test proves
    nothing."""
    src = ('@RestController public class C { @PostMapping("/webhook")'
           ' public String f() { return null; } }')
    fix = _one(findings(src, "x.java", "C"), "REST_GUEST_ACCESS")["fix"]
    for needed in ("Site", "guest user profile", "CORS", "with no session"):
        assert needed in fix
    assert "signature or shared secret" in fix, "the endpoint is open once this is done"


def test_a_get_is_not_treated_as_a_callback():
    """A callback is posted to. Flagging reads would make the rule noise."""
    src = ('@RestController public class C { @GetMapping("/payment/status")'
           ' public String f() { return null; } }')
    assert "REST_GUEST_ACCESS" not in _rules(findings(src, "x.java", "C"))


def test_an_ordinary_post_is_not_flagged():
    src = ('@RestController public class C { @PostMapping("/orders")'
           ' public String f() { return null; } }')
    assert "REST_GUEST_ACCESS" not in _rules(findings(src, "x.java", "C"))


# ── payload ───────────────────────────────────────────────────────────────────

def test_the_heap_bound_is_stated_once_per_controller():
    rows = [r for r in findings(CONTROLLER.read_text(), "x.java", "C")
            if r["rule"] == "REST_PAYLOAD_CAP"]
    assert len(rows) == 1
    assert f"{HEAP_SYNC_MB} MB" in rows[0]["hazard"]
    assert "no streaming" in rows[0]["hazard"]


def test_the_payload_fix_does_not_pretend_paging_always_works():
    fix = _one(findings(CONTROLLER.read_text(), "x.java", "C"), "REST_PAYLOAD_CAP")["fix"]
    assert "Bulk API" in fix or "object storage" in fix


# ── what the builder is told ──────────────────────────────────────────────────

def test_the_builder_is_told_one_class_per_endpoint():
    block = grounding_for([CONTROLLER.read_text()])
    assert "may declare **one** `@HttpGet`" in block
    assert "do not put two in one class" in block


def test_the_builder_is_told_there_is_no_path_variable():
    block = grounding_for([CONTROLLER.read_text()])
    assert "there is no `@PathVariable`" in block
    assert "RestContext.request.requestURI" in block


def test_a_source_with_no_controller_grounds_nothing():
    assert grounding_for(["public class Plain {}"]) == ""
    assert grounding_for([]) == ""


# ── the radar ─────────────────────────────────────────────────────────────────

def test_the_controller_reaches_the_radar():
    from src.radar import scan

    rows = [f for f in scan(str(CONTROLLER.parents[6]))["findings"]
            if f["rule"].startswith("REST_")]
    assert _rules(rows) == {"REST_VERB_COLLISION", "REST_PATH_TEMPLATE", "REST_PAYLOAD_CAP"}


def test_every_integration_rule_has_a_title():
    from src.radar import _RULE_TITLES, rule_title

    for rule in ("REST_VERB_COLLISION", "REST_PATH_TEMPLATE", "REST_GUEST_ACCESS",
                 "REST_PAYLOAD_CAP"):
        assert rule in _RULE_TITLES and rule_title(rule) != rule


# ── E3: an upsert needs a key the target enforces ─────────────────────────────

class _Obj:
    def __init__(self, api, records=1, external_id="Code__c"):
        self.object_api, self.records, self.external_id = api, [1] * records, external_id


def _out(tmp_path, *objects, fields=()):
    base = tmp_path / "force-app/main/default/objects"
    for obj, field in fields:
        (base / obj / "fields").mkdir(parents=True, exist_ok=True)
        if field:
            (base / obj / "fields" / f"{field}.field-meta.xml").write_text("<x/>")
    base.mkdir(parents=True, exist_ok=True)
    from src.impex import upsert_blockers
    return upsert_blockers(str(tmp_path), list(objects))


def test_an_object_that_was_never_generated_is_a_blocker(tmp_path):
    rows = _out(tmp_path, _Obj("Ghost__c"))
    assert rows[0]["reason"] == "no_object"


def test_a_platform_type_is_named_as_one_rather_than_asked_for(tmp_path):
    """`CronJob` configures how the source platform runs. There is no object to load it
    into and there should not be — schedules become code, not records."""
    rows = _out(tmp_path, _Obj("CronJob__c"))
    assert rows[0]["reason"] == "platform_type"
    assert "schedules are generated as scheduled code" in rows[0]["detail"]


def test_an_out_of_the_box_type_points_at_the_standard_object(tmp_path):
    """The same answer 1.32 gives for a relation to `Customer` — a custom twin of a
    standard object is not the fix."""
    rows = _out(tmp_path, _Obj("Customer__c"))
    assert "`Account` or `Contact`" in rows[0]["detail"]
    assert "custom twin" in rows[0]["detail"]


def test_an_object_with_no_unique_column_cannot_be_upserted(tmp_path):
    rows = _out(tmp_path, _Obj("Order__c", external_id=None),
                fields=[("Order__c", None)])
    assert rows[0]["reason"] == "no_key"
    assert "duplicates every record" in rows[0]["detail"]


def test_a_key_whose_field_was_never_generated_is_a_blocker(tmp_path):
    """`mark_external_id_fields` skips a missing file silently, and the runbook still
    prints the upsert command."""
    rows = _out(tmp_path, _Obj("Order__c", external_id="Code__c"),
                fields=[("Order__c", "Other__c")])
    assert rows[0]["reason"] == "no_field"


def test_a_complete_object_is_not_a_blocker(tmp_path):
    assert _out(tmp_path, _Obj("Order__c"), fields=[("Order__c", "Code__c")]) == []


def test_a_data_only_run_reports_nothing(tmp_path):
    """No generated metadata at all means this is a standalone data run, where a missing
    object is expected rather than wrong."""
    from src.impex import upsert_blockers

    assert upsert_blockers(str(tmp_path), [_Obj("Ghost__c")]) == []


def test_the_blockers_reach_the_sign_off(tmp_path):
    from src import assurance
    from src.signoff import _caveats

    blocked = _out(tmp_path, _Obj("Customer__c"))
    claim = {"rung": assurance.REPLAYED, "claim": "", "limit": ""}
    text = "\n".join(_caveats({}, {}, {}, {}, {}, [], claim, upsert_blockers=blocked))
    assert "Data load blocked" in text and "Customer__c" in text
