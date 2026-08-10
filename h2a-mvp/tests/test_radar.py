"""The anti-pattern radar: Hybris habits that become Salesforce hazards.

Half of these test that a rule fires. The other half test that it *doesn't* — which
matters more. A radar with false positives gets switched off in a week, and then the
true findings go with it, so every rule is anchored to structure rather than to a
hopeful substring.
"""

import pathlib
import tempfile
import textwrap

from src.radar import scan, headline, write_radar_md, _loop_lines, _strip


def build(files: dict) -> str:
    d = pathlib.Path(tempfile.mkdtemp())
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return str(d)


def rules(root):
    return {f["rule"] for f in scan(root)["findings"]}


# ── loop detection, which everything critical depends on ──────────────────────

def test_a_call_inside_a_for_body_is_in_a_loop():
    src = "void go(){\n  for (X x : xs)\n  {\n    svc.save(x);\n  }\n}"
    assert 4 in _loop_lines(src)


def test_a_call_after_a_loop_closes_is_not_in_it():
    """Proximity-based detection would flag this; brace tracking does not."""
    src = "void go(){\n  for (X x : xs)\n  {\n    a(x);\n  }\n  svc.save(one);\n}"
    loops = _loop_lines(src)
    assert 4 in loops and 6 not in loops


def test_a_braceless_single_statement_loop_counts():
    src = "void go(){\n  for (X x : xs) svc.save(x);\n}"
    assert 2 in _loop_lines(src)


def test_nested_loops_close_correctly():
    src = ("void go(){\n  for (A a : as)\n  {\n    for (B b : bs)\n    {\n      x();\n"
           "    }\n  }\n  after();\n}")
    loops = _loop_lines(src)
    assert 6 in loops and 9 not in loops


# ── the critical rules ────────────────────────────────────────────────────────

def test_flexible_search_in_a_loop_is_critical():
    found = scan(build({"src/A.java": """
        public class A {
          void go() {
            for (String code : codes) {
              SearchResult<OrderModel> r = flexibleSearchService.search(q);
            }
          }
        }
    """}))["findings"]
    hit = next(f for f in found if f["rule"] == "SOQL_IN_LOOP")
    assert hit["severity"] == "critical"
    assert "governor" in hit["hazard"]
    assert hit["fix"]


def test_save_in_a_loop_is_critical():
    found = scan(build({"src/A.java": """
        public class A {
          void go() {
            for (OrderModel o : orders) {
              modelService.save(o);
            }
          }
        }
    """}))["findings"]
    assert any(f["rule"] == "DML_IN_LOOP" and f["severity"] == "critical" for f in found)


def test_the_same_query_outside_a_loop_is_not_flagged_as_in_one():
    assert "SOQL_IN_LOOP" not in rules(build({"src/A.java": """
        public class A {
          void go() {
            SearchResult<OrderModel> r = flexibleSearchService.search(q);
            for (OrderModel o : r.getResult()) { touch(o); }
          }
        }
    """}))


# ── the guards that stop it crying wolf ───────────────────────────────────────

def test_a_javadoc_warning_about_the_pattern_does_not_fire_the_rule():
    """The most obvious way to make a tool untrustworthy is to have it flag the comment
    telling you not to do the thing."""
    assert not rules(build({"src/A.java": """
        public class A {
          /**
           * Never call modelService.save() inside a loop, and never run
           * flexibleSearchService.search() in one either.
           */
          void go() { modelService.save(one); }
        }
    """})) & {"SOQL_IN_LOOP", "DML_IN_LOOP"}


def test_a_string_literal_mentioning_the_pattern_does_not_fire():
    assert "DML_IN_LOOP" not in rules(build({"src/A.java": """
        public class A {
          void go() {
            for (X x : xs) { log("modelService.save() would be wrong here"); }
          }
        }
    """}))


def test_a_bounded_query_is_not_reported_as_unbounded():
    assert "QUERY_NO_LIMIT" not in rules(build({"src/A.java": """
        public class A {
          void go() {
            final FlexibleSearchQuery query = new FlexibleSearchQuery(Q);
            query.setCount(500);
            flexibleSearchService.search(query);
          }
        }
    """}))


def test_an_unbounded_query_is_reported_but_says_it_may_be_fine():
    found = scan(build({"src/A.java": """
        public class A {
          void go() {
            final FlexibleSearchQuery query = new FlexibleSearchQuery(Q);
            flexibleSearchService.search(query);
          }
        }
    """}))["findings"]
    hit = next(f for f in found if f["rule"] == "QUERY_NO_LIMIT")
    assert "can be dismissed" in hit["fix"], "a lower-confidence rule must say so"


def test_a_final_static_constant_is_not_mutable_state():
    assert "STATIC_MUTABLE_STATE" not in rules(build({"src/A.java": """
        public class A {
          private static final String CODE = "X";
          void go() {}
        }
    """}))


# ── XML rules: the stripper nearly ate these ──────────────────────────────────

def test_a_session_scoped_bean_is_found():
    """XML keeps its meaning inside quotes, so the Java string-stripper erased exactly
    what these rules look for and both silently found nothing."""
    assert "SESSION_SCOPED_BEAN" in rules(build({
        "resources/x-spring.xml": '<beans><bean id="ctx" class="C" scope="session"/></beans>'}))


def test_an_interceptor_mapping_is_found():
    assert "INTERCEPTOR" in rules(build({
        "resources/x-spring.xml":
        '<beans><bean class="de.hybris.platform.servicelayer.interceptor.impl.InterceptorMapping"/></beans>'}))


def test_an_xml_comment_mentioning_an_interceptor_does_not_fire():
    assert "INTERCEPTOR" not in rules(build({
        "resources/x-spring.xml": '<beans><!-- no InterceptorMapping here --></beans>'}))


# ── project-level rules ───────────────────────────────────────────────────────

def test_a_large_impex_load_is_flagged():
    rows = "\n".join(f";CODE{i};value" for i in range(300))
    assert "IMPEX_VOLUME" in rules(build({"resources/impex/big.impex":
                                          "INSERT_UPDATE Product;code;name\n" + rows}))


def test_a_small_impex_load_is_not():
    assert "IMPEX_VOLUME" not in rules(build({"resources/impex/small.impex":
                                              "INSERT_UPDATE Product;code\n;A\n;B\n"}))


def test_a_cronjob_is_flagged_for_concurrency():
    assert "CRONJOB_CONCURRENCY" in rules(build({"src/J.java":
        "public class J extends AbstractJobPerformable<CronJobModel> { }"}))


def test_transactional_and_threading_are_found():
    found = rules(build({"src/A.java": """
        public class A {
          @Transactional
          void go() { ExecutorService pool = null; }
        }
    """}))
    assert {"TRANSACTIONAL", "THREADING"} <= found


# ── output shape ──────────────────────────────────────────────────────────────

def test_findings_are_sorted_worst_first_and_numbered():
    r = scan("../Testing/acme-commerce-hybris")
    sevs = [f["severity"] for f in r["findings"]]
    order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
    assert sevs == sorted(sevs, key=lambda s: order[s]), "a reviewer's first ten minutes are the critical rows"
    assert [f["id"] for f in r["findings"]] == [f"H-{i:03d}" for i in range(1, len(r["findings"]) + 1)]


def test_the_realistic_corpus_trips_the_planted_hazards():
    """The corpus was seeded with these on purpose — if the radar cannot find them there
    it will not find them anywhere."""
    assert {"DML_IN_LOOP", "DAO_CALL_IN_LOOP", "TRANSACTIONAL",
            "SESSION_SCOPED_BEAN", "INTERCEPTOR", "CRONJOB_CONCURRENCY"} <= rules(
                "../Testing/acme-commerce-hybris")


def test_a_clean_codebase_reports_nothing():
    r = scan(build({"src/A.java": "public class A { private static final int X = 1; int go(){ return X; } }"}))
    assert r["summary"]["total"] == 0
    assert "No Hybris-specific migration hazards" in headline(r["summary"])


def test_the_report_leads_with_the_critical_count(tmp_path):
    r = scan("../Testing/acme-commerce-hybris")
    text = open(write_radar_md(str(tmp_path), r), encoding="utf-8").read()
    assert "Migration Hazard Report" in text
    assert "critical finding(s)" in text
    assert "no AI, no org, nothing sent anywhere" in text
