"""What a Hybris `<relation>` becomes, and what the target cannot carry. [1.32, A6]

The engine used to answer this with one branch: `source_card == "one" and target_card ==
"many"` became a Lookup, and every other relation was skipped without a word. On the
reference corpus that is one of three relations converted and two silently gone — a schema
that deploys clean and is missing two thirds of its relationships. The kind of
success-shaped failure this product exists to prevent.

Four things decide the mapping, and only the first was being read:

**Cardinality** picks the shape. Salesforce has no one-to-one relationship type and no
many-to-many one; the first is a Lookup plus a uniqueness rule nothing enforces for you,
the second is a junction object.

**`partof`** picks whether it cascades. A Hybris end marked `partof="true"` is a
composition — those children belong to the parent and are deleted with it. Master-detail
is the only Salesforce relationship that does that. Without this fact every relation
becomes a Lookup, the children outlive their parent, and nothing anywhere says so.

**Whether the other end is a type this extension declares.** Relations routinely point at
out-of-the-box types — `Customer`, `Product` — which have no `__c` object to reference. A
lookup to `Customer__c` is a dangling reference that fails the deploy. These are not
conversions, they are *decisions*: Hybris `Customer` is an Account or a Contact depending
on whether the business sells B2B or B2C, and no static analysis settles that.

**The ceiling.** An object may hold at most two master-detail relationships. Reaching it
forces a demotion, and a demotion silently applied is the original defect again.

Nothing here emits metadata. It decides, records the reason, and names what was lost;
`schema.py` owns naming and emission.
"""

MASTER_DETAIL = "MasterDetail"
LOOKUP = "Lookup"
JUNCTION = "Junction"
UNRESOLVED = "Unresolved"

#: Salesforce allows two master-detail relationships per object.
MD_CEILING = 2

#: Hybris out-of-the-box types whose Salesforce counterpart is a *decision*, not a
#: translation. The value is the candidate set — deliberately plural where the source
#: genuinely does not say which, because collapsing that to one guess is how a wrong data
#: model gets built confidently. Anything absent from this table is reported as unmapped
#: rather than guessed at.
OOTB_TARGETS = {
    "Customer": ("Account", "Contact"),
    "User": ("User",),
    "Product": ("Product2",),
    "Order": ("Order",),
    "Cart": ("Opportunity",),
    "Address": ("Address", "Contact"),
    "Category": ("Product2",),
    "Currency": ("CurrencyType",),
    "Country": ("Address",),
    "Title": ("Contact",),
}


def _shape(rel: dict) -> str:
    return f"{rel.get('source_card', 'many')}-to-{rel.get('target_card', 'many')}"


def _ootb_note(kind: str) -> str:
    targets = OOTB_TARGETS.get(kind)
    if not targets:
        return (f"`{kind}` is not declared in this extension and has no known standard "
                "counterpart. Identify the object it becomes before this relation can "
                "be built.")
    if len(targets) == 1:
        return (f"`{kind}` is an out-of-the-box type; on Salesforce it is the standard "
                f"`{targets[0]}`. A custom `{kind}__c` must not be created for it — point "
                f"the relationship at `{targets[0]}` once the object mapping is agreed.")
    opts = " or ".join(f"`{t}`" for t in targets)
    return (f"`{kind}` is an out-of-the-box type and maps to {opts} depending on how the "
            "business is modelled — B2C customers are usually Contacts under a single "
            "Account, B2B ones are Accounts in their own right. The source does not say "
            "which, so this relation cannot be generated without that decision.")


def decide(relations: list, declared: set) -> list[dict]:
    """One row per source relation: what it becomes, why, and what does not survive.

    `declared` is the set of item type codes this extension defines. An end outside it is
    an out-of-the-box type, and a relationship to a `__c` object that will not exist is a
    deploy failure — so those are reported, never emitted.
    """
    rows: list[dict] = []
    for rel in relations or []:
        src, tgt = rel.get("source_type") or "", rel.get("target_type") or ""
        row = {
            "code": rel.get("code") or f"{src}2{tgt}",
            "source_type": src, "target_type": tgt, "shape": _shape(rel),
            "source_qualifier": rel.get("source_qualifier") or "",
            "target_qualifier": rel.get("target_qualifier") or "",
            "kind": "", "parent": "", "child": "", "cascade": False,
            "why": "", "lost": "", "demoted": False,
        }

        missing = [t for t in (src, tgt) if t and t not in declared]
        if missing:
            row["kind"] = UNRESOLVED
            row["why"] = " ".join(_ootb_note(t) for t in missing)
            row["lost"] = (f"The `{row['code']}` relation is not in the generated schema. "
                           "Records on both sides convert; the link between them does not.")
            rows.append(row)
            continue

        sc, tc = rel.get("source_card", "many"), rel.get("target_card", "many")

        if sc == "many" and tc == "many":
            row.update(
                kind=JUNCTION, parent=src, child=tgt, cascade=True,
                why=("Salesforce has no many-to-many relationship. The standard modelling "
                     "is a junction object holding one master-detail to each side, which "
                     "is also what makes the pair enforceable: a junction row cannot "
                     "exist without both parents."),
                lost=("A junction row is deleted when either parent is, which is the "
                      "right semantics for an association but is a stronger rule than "
                      "Hybris applied — there, removing one side left the other's row "
                      "untouched. Any attribute Hybris stored *on* the relation must be "
                      "moved onto the junction object; this generates the link only."),
            )
            rows.append(row)
            continue

        if sc == "one" and tc == "one":
            row.update(
                kind=LOOKUP, parent=src, child=tgt, cascade=False,
                why=("Salesforce has no one-to-one relationship type. A Lookup on "
                     f"`{tgt}` carries the link; it is the closest available shape."),
                lost=("Nothing enforces the *one*. A Lookup permits many children to "
                      "point at the same parent, so the cardinality Hybris guaranteed "
                      "becomes a convention. Add a uniqueness rule — a unique External "
                      "Id on the lookup, or a validation rule — or duplicates appear "
                      "with no error."),
            )
            rows.append(row)
            continue

        # one-to-many, or its mirror. The `many` end holds the children, so it is the
        # object that gets the field pointing back at the parent.
        if sc == "one":
            parent, child, child_partof = src, tgt, rel.get("target_partof")
            parent_optional = rel.get("source_optional", True)
        else:
            parent, child, child_partof = tgt, src, rel.get("source_partof")
            parent_optional = rel.get("target_optional", True)

        row.update(parent=parent, child=child)
        if child_partof:
            row.update(
                kind=MASTER_DETAIL, cascade=True,
                why=(f"`{child}` is declared `partof` `{parent}`, so it is a composition: "
                     "the children belong to the parent and Hybris deletes them with it. "
                     "Master-detail is the only Salesforce relationship that cascades, so "
                     "a Lookup here would leave orphans behind every parent deletion."),
                lost=("A master-detail child is required and inherits its parent's "
                      "sharing, so `{child}` can no longer be secured independently, and "
                      "every child row must be loaded with its parent already present. "
                      "If any existing row has no parent, the field cannot be created "
                      "until that is fixed.").format(child=child),
            )
            if parent_optional:
                row["lost"] += (f" The `{parent}` end is declared optional, which "
                                "master-detail does not allow — rows with no parent will "
                                "be rejected on load.")
        else:
            row.update(
                kind=LOOKUP, cascade=False,
                why=(f"`{child}` is not `partof` `{parent}` — the children outlive the "
                     "parent in Hybris too — so a Lookup carries the association without "
                     "imposing a cascade delete the source never had."),
                lost="",
            )
        rows.append(row)

    return _apply_ceiling(rows)


def _apply_ceiling(rows: list[dict]) -> list[dict]:
    """Demote master-details past the per-object limit, and say which and why.

    Order is the source's, so the choice is deterministic and reviewable rather than
    whichever relation happened to sort last.
    """
    used: dict[str, int] = {}
    for row in rows:
        if row["kind"] != MASTER_DETAIL:
            continue
        child = row["child"]
        used[child] = used.get(child, 0) + 1
        if used[child] <= MD_CEILING:
            continue
        row.update(
            kind=LOOKUP, cascade=False, demoted=True,
            lost=(f"**Cascade delete is not carried across.** `{child}` is `partof` "
                  f"`{row['parent']}`, but it already holds {MD_CEILING} master-detail "
                  "relationships and Salesforce allows no more. This one is emitted as a "
                  "Lookup so the deploy succeeds, which means deleting a "
                  f"`{row['parent']}` leaves its `{child}` rows behind. Either delete "
                  "them from Apex, or re-model so this composition is one of the two that "
                  "keeps its master-detail."),
        )
    return rows


def unresolved(rows: list[dict]) -> list[dict]:
    """The relations that are not in the schema at all — the ones worth interrupting for."""
    return [r for r in rows if r["kind"] == UNRESOLVED]
