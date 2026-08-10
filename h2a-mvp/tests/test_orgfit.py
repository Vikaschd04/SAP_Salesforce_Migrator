"""Target-org fit: will this package actually deploy into *their* org?

Tested against synthetic org descriptions rather than a live org — the point is the
reconciliation logic, and a test that needs someone to be logged in is a test that does
not run.
"""

from src.orgfit import assess, headline, write_orgfit_md


def org(objects=(), namespaces=(), limits=None, username="ada@acme.com"):
    return {"username": username, "instance_url": "https://x.my.salesforce.com",
            "api_version": "60.0", "is_scratch": False,
            "objects": list(objects), "custom_objects": [o for o in objects if o.endswith("__c")],
            "namespaces": list(namespaces), "limits": limits or {}}


def kinds(fit):
    return {f["kind"] for f in fit["findings"]}


def test_no_org_is_reported_not_raised():
    """An advisory that blocks a run when it cannot reach an org is worse than none."""
    fit = assess({"Order": {}}, None)
    assert fit["connected"] is False and fit["findings"] == []
    assert "not inspected" in headline(fit)


def test_a_name_collision_is_critical():
    """The classic day-one failure: inventing an object the org has had for years."""
    fit = assess({"LoyaltyAccount": {}}, org(["Account", "LoyaltyAccount__c"]))
    hit = next(f for f in fit["findings"] if f["kind"] == "collision")
    assert hit["severity"] == "critical" and hit["object"] == "LoyaltyAccount__c"
    assert "already has" in hit["detail"]


def test_a_standard_object_is_offered_instead_of_a_parallel_custom_one():
    fit = assess({"Order": {}}, org(["Order", "OrderItem", "Account"]))
    hit = next(f for f in fit["findings"] if f["kind"] == "reusable")
    assert "Order" in hit["fix"] and hit["severity"] == "high"


def test_an_unrelated_custom_object_is_not_flagged():
    assert assess({"SubscriptionPlan": {}}, org(["Account", "Widget__c"]))["findings"] == []


def test_an_installed_package_strengthens_the_planner_flag():
    """CPQ present turns 'consider CPQ' from a suggestion into 'you already own this'."""
    fit = assess({"Widget": {}}, org(["Account"], namespaces=["SBQQ"]))
    hit = next(f for f in fit["findings"] if f["kind"] == "package")
    assert "CPQ" in hit["object"] and "Configure" in hit["fix"]


def test_exhausted_custom_object_headroom_is_critical():
    fit = assess({f"Obj{i}": {} for i in range(30)},
                 org(["Account"], limits={"CustomObjects": {"max": 400, "remaining": 5}}))
    hit = next(f for f in fit["findings"] if f["kind"] == "headroom")
    assert hit["severity"] == "critical" and "5 of 400" in hit["detail"]


def test_sufficient_headroom_is_not_flagged():
    fit = assess({"A": {}}, org(["Account"], limits={"CustomObjects": {"max": 400, "remaining": 300}}))
    assert "headroom" not in kinds(fit)


def test_findings_are_worst_first():
    fit = assess({"Order": {}, "LoyaltyAccount": {}},
                 org(["Order", "LoyaltyAccount__c", "Account"]))
    assert fit["findings"][0]["severity"] == "critical"


def test_a_clean_org_says_so_by_name():
    fit = assess({"SubscriptionPlan": {}}, org(["Account"]))
    assert fit["summary"]["total"] == 0
    assert "looks clear" in headline(fit) and "ada@acme.com" in headline(fit)


def test_the_report_explains_the_cost_of_finding_this_late(tmp_path):
    fit = assess({"Order": {}}, org(["Order", "Account"]))
    text = open(write_orgfit_md(str(tmp_path), fit), encoding="utf-8").read()
    assert "Target Org Fit" in text
    assert "costs the deploy" in text


def test_the_report_is_still_written_with_no_org(tmp_path):
    text = open(write_orgfit_md(str(tmp_path), assess({"A": {}}, None)), encoding="utf-8").read()
    assert "sf org login web" in text
