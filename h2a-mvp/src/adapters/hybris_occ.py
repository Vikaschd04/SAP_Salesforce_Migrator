"""A Magento storefront controller, as an OCC REST endpoint. [1.53]

Migrating the Appointment module surfaced this: seven of its twenty targets are
controllers, and every one emitted as a Spring service. The Java was correct and the
result was wrong — `DefaultCreateService` gives a Hybris developer no way to know that
`/appointment/index/create` used to reach it, or that it was an entry point at all. The
route was never even read; `etc/routes.xml` was the one `etc/` file the adapter skipped.

**Why OCC rather than a storefront controller.** A Magento controller returns a rendered
page. SAP Commerce has two answers to that, and they are not equally alive: the accelerator
storefront's `@Controller` returns a JSP view, while a Spartacus front end calls an OCC
REST endpoint and renders in the browser. Spartacus is the current default, so an endpoint
is the more useful target — and it is also the more honest one, because a REST method that
returns a DTO is obviously incomplete in a way that a controller returning a view name is
not.

**What is derived and what is not.** The route, the HTTP method and the class are derived:
the URL comes from `routes.xml` plus Magento's directory convention, and the verb from
what the action does to state. The *body* is not, and neither is the DTO — a Magento
controller reads `getRequest()->getParams()` and writes a rendered result, and neither has
a shape until someone decides what this endpoint's contract is. So the DTO is named and
left for a person, and that is said in the file rather than filled in with a guess.

Admin controllers are not emitted here at all. `Controller/Adminhtml/...` is reached
through Backoffice on the target, and the Backoffice configuration this migration already
writes covers the list and the editor — turning an admin action into a public REST
endpoint would expose an internal operation to the storefront, which is a security
decision nobody asked for.
"""

from __future__ import annotations

from src.adapters.hybris_extension import pascal

#: Magento action names that change state, and the verb each becomes. Anything not listed
#: is treated as a read, because GET is the safe default: a wrongly-GET endpoint is a bug
#: a reviewer sees immediately, while a wrongly-POST one silently invites writes.
_WRITES = {
    "save": "PostMapping", "create": "PostMapping", "add": "PostMapping",
    "post": "PostMapping", "submit": "PostMapping",
    "update": "PutMapping", "edit": "PutMapping",
    "delete": "DeleteMapping", "remove": "DeleteMapping", "destroy": "DeleteMapping",
}


def _verb(action: str) -> str:
    return _WRITES.get((action or "").lower(), "GetMapping")


def controller_name(unit_name: str, route: dict) -> str:
    """`AppointmentCreateController` — the front name plus the action.

    Named from the *route* rather than the PHP class, because three of the Appointment
    module's controllers are called `Index` and a class name alone collides. The URL is
    what makes them different, so the URL is what names them.
    """
    front = pascal((route or {}).get("front_name", "") or "")
    action = pascal(unit_name or "")
    if action.lower() == "index":
        segs = [s for s in ((route or {}).get("path", "") or "").split("/") if s]
        action = pascal(segs[-1]) if len(segs) > 1 else ""
    return f"{front}{action}Controller" if front else f"{action}Controller"


def dto_name(route: dict) -> str:
    front = pascal((route or {}).get("front_name", "") or "Resource")
    return f"{front}WsDTO"


def build_controller(unit, package: str, route: dict, *, generated_class: str = "",
                     bodies: dict | None = None) -> str:
    """The OCC endpoint for one storefront controller."""
    from src.adapters import java_bodies

    name = controller_name(getattr(unit, "name", ""), route)
    dto = dto_name(route)
    action = (route or {}).get("action", "") or "execute"
    verb = _verb(action)
    method = _method_name(action)
    path = (route or {}).get("path", "") or ""
    # OCC namespaces every endpoint under the site, which Magento has no equivalent of:
    # one Magento install serves one storefront, and one Commerce install serves many.
    sub = "/".join(p for p in path.split("/")[1:] if p)

    # What this endpoint is about to declare. Stated to the merge rather than left
    # implicit, because an OCC signature is derived from the *route* — a path variable and
    # a request parameter — while the Magento `execute()` it came from took no parameters
    # and returned a rendered page. Those are not the same method, and merging one into
    # the other produced a controller whose body read `records` under a signature
    # declaring `baseSiteId, code`: `cannot find symbol`, twice, plus a return type that
    # could not match. The check belongs here because only this emitter knows what it is
    # about to write. [4.7]
    merge = java_bodies.plan_merge(
        generated_class, {method: [method, action, "execute"]},
        contracts={method: {"params": ["baseSiteId", "code"],
                            "known": {"dataMapper"}}})

    out = [f"package {package}.controllers;", "",
           "import de.hybris.platform.webservicescommons.mapping.DataMapper;",
           "import org.springframework.beans.factory.annotation.Autowired;",
           "import org.springframework.http.MediaType;",
           f"import org.springframework.web.bind.annotation.{verb};",
           "import org.springframework.web.bind.annotation.PathVariable;",
           "import org.springframework.web.bind.annotation.RequestMapping;",
           "import org.springframework.web.bind.annotation.RequestParam;",
           "import org.springframework.web.bind.annotation.RestController;",
           # The response type sits in its own package, so the controller needs it by
           # name. A missing import here is exactly the class of defect the stub compiler
           # was added to catch, and it costs nothing to not make it.
           f"import {package}.dto.{dto};"]
    out += [i for i in merge["imports"] if i not in out]
    out += ["",
            "/**",
            f" * Migrated from the Adobe Commerce controller {getattr(unit, 'name', '')}"
            f" ({getattr(unit, 'file', '')}).",
            " *",
            f" * Answered `/{path}` on Magento. A Spartacus storefront reaches the same",
            f" * behaviour through this endpoint; the `{{baseSiteId}}` segment is OCC's and",
            " * has no Magento counterpart — one Magento install serves one storefront,",
            " * one Commerce install serves many, so the site has to be named here.",
            " *",
            f" * `{verb[:-7].upper()}` because the Magento action was `{action}`.",
            " *",
            " * TO FINISH: the request and response shapes. A Magento controller reads",
            f" * `getRequest()->getParams()` and returns a rendered page, so `{dto}` has",
            " * no fields yet — nothing in the source says what this endpoint's contract",
            " * is, and inventing one would be inventing an API.",
            " */",
            "@RestController",
            f'@RequestMapping(value = "/{{baseSiteId}}/{sub}")' if sub
            else '@RequestMapping(value = "/{baseSiteId}")',
            f"public class {name}", "{", "",
            "    @Autowired", "    private DataMapper dataMapper;"]

    if merge["fields"]:
        out.append("")
        out += [f"    {f}" for f in merge["fields"]]

    out += ["",
            f'    @{verb}(produces = MediaType.APPLICATION_JSON_VALUE)',
            f"    public {dto} {method}(@PathVariable final String baseSiteId,",
            "            @RequestParam(required = false) final String code)", "    {"]
    if merge["bodies"]:
        out.append(f"        // Generated from {getattr(unit, 'name', '')}::{action}."
                   " Reviewed as generated logic, not derived — see PROVENANCE.md.")
        out += java_bodies.indent(merge["bodies"][method])
    else:
        out += [f"        // TODO migrate: {getattr(unit, 'name', '')}::{action}"]
        # A body that was written and then refused is a different situation from one that
        # was never written, and the reviewer is the person who can act on the difference:
        # there is logic to look at, in the run's own record, and a reason it is not here.
        # Dropping it silently makes a refused body indistinguishable from an absent one.
        why = merge["rejected"].get(method)
        if why:
            out += [f"        // A body WAS generated for this endpoint and was not used:",
                    f"        // {why}.",
                    "        // It is preserved in the run's artifact record — review it "
                    "there before",
                    "        // writing this method, rather than starting from nothing."]
        out += ["        throw new UnsupportedOperationException(",
                f'                "Not migrated yet: {path}");']
    out.append("    }")

    for _hn, hs in sorted(merge["helpers"].items()):
        out += ["", "    // Generated helper, called by the logic above."]
        out += [("    " + ln) if ln.strip() else "" for ln in hs.splitlines()]

    out += ["}", ""]
    return "\n".join(out)


def _method_name(action: str) -> str:
    a = (action or "execute").strip()
    return a[:1].lower() + a[1:] if a else "execute"


def build_dto(route: dict, package: str) -> str:
    """The response shape, declared empty and said so.

    Emitted rather than skipped because the controller will not compile without it, and a
    named empty type is a better prompt to a reviewer than a missing one: it appears in
    the tree, it has a TODO, and it is where the contract goes when someone decides it.
    """
    name = dto_name(route)
    return "\n".join([
        f"package {package}.dto;", "",
        "/**",
        f" * Response for `/{(route or {}).get('path', '')}`.",
        " *",
        " * Deliberately empty. The Magento controller it came from returned a rendered",
        " * page, so there is no field list anywhere in the source to carry across —",
        " * what this endpoint returns is an API design decision, not a translation.",
        " *",
        " * TO FINISH: add the fields this endpoint should return, and map them in the",
        " * controller with the injected `DataMapper`.",
        " */",
        f"public class {name}", "{", "", "}", ""])


def manual_reason(unit_name: str, route: dict) -> str:
    """Why an admin controller is not emitted as an endpoint."""
    return (f"`{unit_name}` is a Magento *admin* controller (`/{route.get('path', '')}`). "
            "On the target, admin CRUD is Backoffice — the list view and editor for its "
            "item type are already generated in the backoffice config. Emitting it as an "
            "OCC endpoint would publish an internal operation to the storefront, which is "
            "a security decision nobody has asked for.")
