"""Magento's admin UI, as Hybris Backoffice configuration. [1.41]

Magento declares its admin grids and forms in UI-component XML and backs them with PHP
column and button classes. Hybris does the same job in `*-backoffice-config.xml`, which is
also declarative — so the halves do not port the same way, and saying "admin UI has no
equivalent" was wrong about the larger half.

**What is derivable, and is generated here.** A list view, an editor area and an advanced
search for every item type this migration declares. All three come from `items.xml`, which
this migration writes, so the columns and fields are exactly the attributes that will
exist. Nothing is guessed.

**What is not, and is reported instead.** A custom button (`SaveButton`, `BackButton`) or a
column action is a *widget with behaviour* — it does something when clicked, and what it
should do on the target is a decision about the target's own UI, not a translation. Those
stay on the manual list with that reason.

**One judgement, stated rather than hidden.** A list view showing eighteen columns is
unusable, so attributes are *ranked* by how much they identify a record — unique first,
then the naming ones, then foreign keys, then timestamps, with long free text last — and
the top few become columns while the editor shows everything. Ranking rather than
filtering, because "required" is no signal at all on a Magento table where almost every
column is `nullable="false"`. That is a choice about *presentation*, it changes no data,
and the generated file says so in a comment so the first person to open it knows it is
theirs to change.
"""

from __future__ import annotations

from src.adapters.hybris_extension import pascal

#: Attributes worth a column. A record is found by what identifies it; the rest are read
#: in the editor once the row is open.
_LIST_LIMIT = 8


def _attributes(data_type) -> list:
    d = data_type.to_dict() if hasattr(data_type, "to_dict") else dict(data_type or {})
    return [a for a in (d.get("attributes") or d.get("fields") or []) if isinstance(a, dict)]


def _type_code(data_type) -> str:
    d = data_type.to_dict() if hasattr(data_type, "to_dict") else dict(data_type or {})
    return pascal(d.get("code") or d.get("name") or "")


def _list_columns(attrs: list) -> list:
    """Identifying attributes first, then whatever fills the row out.

    Ranked rather than filtered. "Required" is not a useful signal on a Magento table
    where almost every column is `nullable="false"` — it selected seven of eight columns
    including the free-text address, and left the foreign key and the timestamps out.
    """
    def rank(a: dict) -> tuple:
        name = a.get("name", "")
        if a.get("unique"):
            return (0, name)
        if name in ("code", "name", "title", "label", "email", "status"):
            return (1, name)
        if name.endswith("_id"):
            return (2, name)
        if name.endswith("_at") or a.get("type") in ("DateTime", "Date"):
            return (3, name)
        # Long free text reads badly in a grid cell and tells a reader nothing at a
        # glance, so it sinks below everything that does.
        if a.get("raw_type") in ("text", "mediumtext", "longtext"):
            return (5, name)
        return (4, name)

    ranked = sorted((a for a in attrs if a.get("name") != "entity_id"), key=rank)
    return ranked[:_LIST_LIMIT]


def build_config(data_model, extension: str) -> str:
    """`<extension>-backoffice-config.xml` for every generated item type."""
    types = [t for t in (getattr(data_model, "types", None) or [])
             if getattr(t, "deployment", "") != "eav"]

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<config xmlns="http://www.hybris.com/cockpit/config"',
           '        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
           '        xmlns:list-view="http://www.hybris.com/cockpitng/component/listView"',
           '        xmlns:editorArea="http://www.hybris.com/cockpitng/component/editorArea"',
           '        xmlns:advanced-search="http://www.hybris.com/cockpitng/config/advancedsearch">',
           "",
           "    <!-- Generated from items.xml, so every column and field below is an",
           "         attribute that will exist. The *choice of which* attributes appear in",
           "         the list is a presentation decision and yours to change: identifying",
           "         attributes are shown, the rest are in the editor. -->",
           ""]

    for dt in types:
        code = _type_code(dt)
        if not code:
            continue
        attrs = _attributes(dt)

        out += [f'    <context merge-by="type" parent="GenericItem" type="{code}"',
                '             component="listview">',
                "        <list-view:list-view>"]
        out += [f'            <list-view:column qualifier="{a["name"]}"/>'
                for a in _list_columns(attrs)]
        out += ["        </list-view:list-view>", "    </context>", ""]

        out += [f'    <context merge-by="type" type="{code}" component="editor-area">',
                "        <editorArea:editorArea>",
                "            <editorArea:essentials/>",
                '            <editorArea:tab name="hmc.tab.essential">',
                '                <editorArea:section name="hmc.section.common">']
        out += [f'                    <editorArea:attribute qualifier="{a["name"]}"/>'
                for a in attrs if a.get("name")]
        out += ["                </editorArea:section>",
                "            </editorArea:tab>",
                "        </editorArea:editorArea>",
                "    </context>", ""]

        out += [f'    <context type="{code}" component="advanced-search">',
                "        <advanced-search:advanced-search>",
                "            <advanced-search:field-list>"]
        out += [f'                <advanced-search:field name="{a["name"]}" selected="true"/>'
                for a in _list_columns(attrs)]
        out += ["            </advanced-search:field-list>",
                "        </advanced-search:advanced-search>",
                "    </context>", ""]

    out += ["</config>", ""]
    return "\n".join(out)


def manual_reason(unit_name: str) -> str:
    """Why a button or a column action is not generated.

    Specific on purpose. The generic "no emitter for this kind yet" is true and useless:
    it reads as a gap in the tool, when the actual answer is that this class does
    something when a person clicks it and nobody has said what it should do afterwards.
    """
    return (f"`{unit_name}` is a Backoffice *widget*, not configuration. The list view and "
            "editor for its item type are generated in the backoffice config; this class "
            "is behaviour attached to a control — what it should do on the target is a "
            "decision about the target's own UI, and generating a plausible one would be "
            "inventing a workflow nobody specified.")
