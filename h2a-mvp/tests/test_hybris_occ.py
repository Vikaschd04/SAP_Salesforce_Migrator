"""A Magento controller is an entry point, not a bean. [1.53]

Migrating a real third-party module — the MageMonk Appointment module, vendored under
`Testing/appointment-magento` — put seven controllers through the planner and got seven
Spring services. The Java was correct and the result was wrong: `DefaultCreateService`
gives a Hybris developer no way to know that `/appointment/create` used to reach it, or
that it was an entry point at all.

The route was never read. `etc/routes.xml` was the one `etc/` file the adapter skipped, so
a controller arrived as an ordinary class with an `execute()` method and nothing to
distinguish it. The planner's own comment admitted the deferral — "the endpoint itself is
a separate decision about the storefront" — and this is that decision.

Storefront actions become OCC endpoints, which is what a Spartacus front end calls. Admin
actions do not: admin CRUD is Backoffice, whose configuration this migration already
writes, and republishing an internal operation as a public REST endpoint is a security
decision nobody asked for.
"""

import pathlib

import pytest

from src.adapters import hybris_occ
from src.adapters.hybris_plan import CONTROLLER, MANUAL, plan_targets
from src.adapters.magento_config import read_routes, route_for

CORPUS = str(pathlib.Path(__file__).resolve().parents[2] / "Testing" / "appointment-magento")


@pytest.fixture(scope="module")
def routes():
    return read_routes(CORPUS)


# ── the URL is assembled, not stored ──────────────────────────────────────────

def test_the_front_name_is_read_from_routes_xml(routes):
    assert routes["frontend"]["appointment"] == "appointment"


def test_the_two_areas_are_kept_apart(routes):
    """They reach different subsystems on the target, so folding them together would
    lose exactly the distinction that decides which."""
    assert set(routes) == {"frontend", "adminhtml"}


@pytest.mark.parametrize("path,expected", [
    ("Controller/Index/Create.php", "appointment/create"),
    ("Controller/Index/Address.php", "appointment/address"),
    ("Controller/Customer/Index.php", "appointment/customer"),
    # `Index` is Magento's default at both levels, so this is the bare route.
    ("Controller/Index/Index.php", "appointment"),
])
def test_the_route_follows_magentos_directory_convention(routes, path, expected):
    assert route_for(path, routes)["path"] == expected


def test_a_class_outside_controller_has_no_route(routes):
    assert route_for("Model/Appointment.php", routes) == {}


def test_an_admin_controller_is_marked_as_such(routes):
    assert route_for("Controller/Adminhtml/Index/Save.php", routes)["area"] == "adminhtml"


# ── where each one goes ───────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def plan():
    from src.adapters.adobe_source import ADAPTER

    m = ADAPTER.read(CORPUS)
    return plan_targets(m.units, m.extra["di"], m.extra.get("routes")), m


def test_storefront_controllers_become_endpoints(plan):
    rows, _ = plan
    names = {t["target_name"] for t in rows if t["kind"] == CONTROLLER}
    assert names == {"AppointmentController", "AppointmentCreateController",
                     "AppointmentAddressController", "AppointmentCustomerController"}


def test_admin_controllers_do_not(plan):
    """Publishing an admin action as a public REST endpoint is a security decision, and
    the Backoffice config this migration writes already covers admin CRUD."""
    rows, _ = plan
    admin = [t for t in rows
             if "Adminhtml" in (t["source_classes"][0].get("file") or "")
             and t["source_classes"][0]["file"].startswith("Controller/")]
    assert admin, "the corpus has admin controllers"
    assert all(t["kind"] == MANUAL for t in admin)
    assert all("Backoffice" in t["rationale"] for t in admin)


def test_a_controller_is_named_by_its_route_not_its_class(plan):
    """Three of this module's controllers are literally called `Index`. Named by class
    they collided: `_merge` folded them and disambiguation split them apart again, handing
    both halves the rationale of whichever won — so one endpoint claimed another's URL."""
    rows, _ = plan
    by_file = {t["source_classes"][0]["file"]: t for t in rows if t["kind"] == CONTROLLER}
    assert by_file["Controller/Index/Index.php"]["target_name"] == "AppointmentController"
    assert by_file["Controller/Customer/Index.php"]["target_name"] == \
        "AppointmentCustomerController"


def test_each_rationale_names_that_controllers_own_route(plan):
    rows, _ = plan
    by_file = {t["source_classes"][0]["file"]: t for t in rows if t["kind"] == CONTROLLER}
    assert "/appointment`" in by_file["Controller/Index/Index.php"]["rationale"]
    assert "/appointment/customer`" in by_file["Controller/Customer/Index.php"]["rationale"]


def test_without_routes_a_controller_still_becomes_a_service(plan):
    """A module whose `routes.xml` is missing still has logic worth carrying, and a
    service is the honest home for logic whose entry point is unknown."""
    _, m = plan
    rows = plan_targets(m.units, m.extra["di"], routes=None)
    ctrl = [t for t in rows if (t["source_classes"][0].get("file") or "").startswith("Controller/")]
    assert ctrl and all(t["kind"] != CONTROLLER for t in ctrl)


# ── what is written ───────────────────────────────────────────────────────────

def _controller(path, routes, **kw):
    unit = type("U", (), {"name": pathlib.Path(path).stem, "file": path,
                          "methods": [], "extra": {}})()
    return hybris_occ.build_controller(unit, "com.x", route_for(path, routes), **kw)


def test_the_verb_follows_what_the_action_did(routes):
    """GET is the default because the failure modes are not symmetric: a wrongly-GET
    endpoint is a bug a reviewer sees, a wrongly-POST one silently invites writes."""
    assert "@PostMapping" in _controller("Controller/Index/Create.php", routes)
    assert "@GetMapping" in _controller("Controller/Index/Address.php", routes)


def test_the_route_is_namespaced_under_the_site(routes):
    """OCC serves many storefronts from one install; Magento serves one. The site has to
    be named, and it has no Magento counterpart."""
    out = _controller("Controller/Index/Create.php", routes)
    assert '@RequestMapping(value = "/{baseSiteId}/create")' in out


def test_the_dto_is_imported(routes):
    """It lives in its own package. A missing import here is the exact class of defect
    the stub compiler was added to catch."""
    assert "import com.x.dto.AppointmentWsDTO;" in _controller(
        "Controller/Index/Create.php", routes)


def test_the_response_shape_is_left_open_and_says_so(routes):
    """A Magento controller returns a rendered page, so nothing in the source says what
    this endpoint returns. Inventing fields would be inventing an API."""
    dto = hybris_occ.build_dto(route_for("Controller/Index/Create.php", routes), "com.x")
    assert "TO FINISH" in dto
    assert "public class AppointmentWsDTO" in dto


def test_an_ungenerated_endpoint_refuses_rather_than_returning_null(routes):
    out = _controller("Controller/Index/Create.php", routes)
    assert "UnsupportedOperationException" in out
    assert "appointment/create" in out


def test_generated_logic_is_merged_and_marked(routes):
    out = _controller(
        "Controller/Index/Create.php", routes,
        generated_class="public class X {\n"
                        "    public AppointmentWsDTO create(String baseSiteId, String code) {\n"
                        "        return build(code);\n    }\n"
                        "    private AppointmentWsDTO build(String c) {\n"
                        "        return null;\n    }\n}")
    assert "return build(code);" in out
    assert "Reviewed as generated logic" in out
    assert "private AppointmentWsDTO build(String c)" in out, "the helper came across"
