# Provenance — a slice of a real module, for demonstrations

Eight PHP files taken **unmodified** from the MageMonk Appointment module, chosen so one
short run exercises every part of the Adobe→Hybris pipeline. The full module lives beside
this one in `Testing/appointment-magento`; use that when the question is *coverage*, and
this when the question is *does it work*.

| | |
|---|---|
| **Upstream** | https://github.com/mage-monk/Appointment |
| **Licence** | OSL-3.0 / AFL-3.0 — redistribution permitted with attribution |
| **Author** | Prince Kumar (prince.lpu1991@gmail.com) |
| **Modified** | **No.** Files were selected, never edited. |

## Why these files

Together they form one coherent vertical slice — a data model, the query that reads it,
the service that owns the rules, and the URL a storefront calls — so the migration has to
do every interesting thing once rather than one thing twenty times:

| File | Exercises |
|---|---|
| `etc/db_schema.xml` | `items.xml` generation, and the modelling decisions the source does not settle |
| `Model/ResourceModel/Appointment*.php` | DAO with FlexibleSearch |
| `Api/…Interface.php` + `Model/AppointmentRepository.php` | a service interface and its `Default*` implementation, collapsed via a `di.xml` preference |
| `Controller/Index/Create.php` | an OCC REST endpoint, with its route read from `routes.xml` |
| `etc/di.xml` | preference and plugin wiring |

## The honest part

A slice is not the module. It says nothing about how the migration copes with the four
admin controllers, the Backoffice buttons, the UI component or the GraphQL resolvers that
were left behind — those are exactly where the full run reports its manual work. Anyone
shown this should be told it is a slice; the point of it is a fast, cheap, *real* answer to
"does the thing work", not a claim about scope.

Nothing here should ever be edited to make a migration succeed. The moment it is, it stops
being evidence.
