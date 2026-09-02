# Adobe Commerce → SAP Hybris — knowledge pack

**Scaffold.** The directory exists so the pack machinery is exercised against two
pipelines; the contents are Phase 3 work.

A pack is the platform-pair knowledge a migration runs on, and it is data rather than
code — which is most of what makes a second pipeline adapters-plus-content instead of a
rewrite. To fill this one in, copy the shape of `../hybris_to_salesforce/`:

| File | What it holds | Item |
|---|---|---|
| `prompts/comprehend.txt` | How the model is asked to read a **PHP** class — its purpose, business rules, risks | 2.3 |
| `prompts/generate.txt` | Translate a comprehended unit into **Java/Spring**, not Apex | 3.2 |
| `prompts/generate_system.txt` | The standing rules: Hybris idiom, FlexibleSearch, no Jalo, service/DAO split | 3.2 |
| `prompts/repair.txt` | Feed real `javac` errors back for a bounded rewrite | 3.12 |
| `mappings.yaml` | Magento layer → Hybris artifact kind, with the rules for each | 3.2 |
| `knowledge/*.md` | RAG corpus: Hybris extension layout, ImpEx, FlexibleSearch, business processes | 3.8 |

## Two things not to copy from the Salesforce pack

**The generation prompt must not ask for Apex.** It opens *"Translate the following SAP
Hybris class into Salesforce Apex"* — a prompt that survives a careless copy and produces
confidently wrong output in the right file names.

**The RAG corpus must be replaced, not extended.** Grounding a Java target in Apex governor
limits and fflib patterns would be worse than not grounding it at all: the model would cite
real-sounding constraints that do not exist on the target platform.
