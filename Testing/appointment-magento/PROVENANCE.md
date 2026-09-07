# Provenance — this corpus is not ours

Vendored verbatim from a third-party Magento 2 module, so the migration is exercised
against code nobody here wrote. Every defect worth finding in this project has come from
real modules rather than fixtures: hand-written corpora only contain the shapes their
author already had in mind.

| | |
|---|---|
| **Upstream** | https://github.com/mage-monk/Appointment |
| **Commit** | `b9c38f391b16d5f64fb3bfc064197a5d47465293` |
| **Author** | Prince Kumar (prince.lpu1991@gmail.com) |
| **Licence** | OSL-3.0 / AFL-3.0 — redistribution permitted with attribution |
| **Modified** | No. `.git` removed and this file added; no source file touched. |

The upstream `composer.json` requires `mage-monk/module-base`, which is **not** vendored.
That dependency is absent on purpose: a migration has to cope with a module whose
supertypes it cannot see, and pretending otherwise would make this corpus easier than the
real thing.

Nothing here should ever be edited to make a migration succeed. The moment it is, it stops
being evidence.
