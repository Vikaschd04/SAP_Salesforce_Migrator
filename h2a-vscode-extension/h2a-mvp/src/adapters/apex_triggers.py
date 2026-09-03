"""
apex_triggers.py — re-creating the invocation a lifecycle hook lost. [1.21b]

The logic of a Hybris interceptor converts fine. What does not convert is the fact that
the platform *called* it. Apex has no equivalent: a class runs when something calls it, so
without a trigger the migrated rules sit there, correct and unenforced.

What is emitted is a **scaffold**, and it is labelled one. The trigger itself is fully
determined — the object, the events, the bulk shape, the re-entry guard — and all of that
is written properly, because it is the part teams most often get wrong and it does not
depend on anything a model produced. The one thing left open is the call into the
converted class, because its method signature was written by a model and inventing a call
to a method that may not exist would turn a scaffold into a lie that does not compile.

That split is deliberate: everything knowable is written, the single unknowable thing is
marked, and the completeness ledger says `scaffolded` rather than `converted`.
"""

from __future__ import annotations

TRIGGER_META = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<ApexTrigger xmlns="http://soap.sforce.com/2006/04/metadata">\n'
                "    <apiVersion>60.0</apiVersion>\n    <status>Active</status>\n"
                "</ApexTrigger>\n")

# The handler is an Apex class, and an Apex class without its -meta.xml does not deploy.
# Emitting the .cls alone would have produced a scaffold that fails at the one moment it
# is supposed to help.
CLASS_META = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
              "    <apiVersion>60.0</apiVersion>\n    <status>Active</status>\n"
              "</ApexClass>\n")


def _handler(obj: str, handler: str, hook: dict, converted: str) -> str:
    plural = "records" if hook["events"] != "before delete" else "records being deleted"
    return f"""public with sharing class {handler} {{
    // Re-entry guard. A Hybris interceptor chain does not re-enter; an Apex trigger does,
    // because any DML performed here fires the trigger again. Without this flag a rule
    // that updates its own record recurses until the platform throws
    // "maximum trigger depth exceeded" — in production, from code that passed every test.
    @TestVisible
    private static Boolean running = false;

    public static Boolean isRunning() {{
        return running;
    }}

    public static void handle(List<{obj}> records, Map<Id, {obj}> oldMap) {{
        if (running) {{
            return;
        }}
        running = true;
        try {{
            apply(records, oldMap);
        }} finally {{
            running = false;
        }}
    }}

    private static void apply(List<{obj}> records, Map<Id, {obj}> oldMap) {{
        // SCAFFOLD — not wired up yet.
        //
        // In Hybris, `{hook['hook']}` {hook['note']} for every {obj.replace('__c', '')},
        // one record at a time, invoked by the persistence layer. The rules themselves
        // were converted into `{converted}`; what was lost is that something called them.
        //
        // To finish: call the converted logic for each record below. Its signature was
        // written by the migration and is not assumed here — check it, then wire it in.
        //
        // Keep every SOQL query and every DML statement OUT of this loop. The platform
        // handed the interceptor one record; a trigger receives up to 200, so a lookup
        // that was one query in Hybris becomes 200 here and breaches the governor limit
        // on the first realistic batch. Query before the loop, into a Map.
        for ({obj} record : {plural}) {{
            // TODO: {converted}.<method>(record);
        }}
    }}
}}
"""


def _trigger(obj: str, trigger: str, handler: str, hook: dict, source: str) -> str:
    return f"""trigger {trigger} on {obj} ({hook['events']}) {{
    // Restores an invocation the migration could not carry across.
    //
    // `{source}` implemented `{hook['hook']}`, which SAP Hybris ran automatically — it
    // {hook['note']}. Apex has no such mechanism, so the converted class would never run
    // and the rules it enforced would silently stop being enforced. This trigger is that
    // missing invocation.
    {handler}.handle(Trigger.new, Trigger.oldMap);
}}
"""


def emit_for(source_class: str, target_class: str, hook: dict) -> dict:
    """Files for one lifecycle hook, or {} when Apex has no equivalent to offer.

    `LoadInterceptor` returns nothing on purpose: Apex has no after-read hook, and a
    trigger that could never fire is worse than an honest gap in the ledger.
    """
    if not hook.get("events") or not hook.get("type"):
        return {}
    obj = f"{hook['type']}__c"
    trigger = f"{hook['type']}LifecycleTrigger"
    handler = f"{hook['type']}LifecycleHandler"
    return {
        f"triggers/{trigger}.trigger": _trigger(obj, trigger, handler, hook, source_class),
        f"triggers/{trigger}.trigger-meta.xml": TRIGGER_META,
        f"classes/{handler}.cls": _handler(obj, handler, hook, target_class),
        f"classes/{handler}.cls-meta.xml": CLASS_META,
    }
