# Provenance and acknowledgements

## Project

LANA was built for **Siriraj × MIT Hacking Medicine 2026**. The project team reports **3rd Place**. The award statement identifies the team's placement; no organiser logos or endorsement seals are used.

## Application source

`apps/platform/` is derived from the `mvp/` directory in [modellismz/lana-platform-mvp](https://github.com/modellismz/lana-platform-mvp/tree/e13b0aa2052f3bedc3e1eefd249fdae4100e0196/mvp), commit `e13b0aa2052f3bedc3e1eefd249fdae4100e0196`. The original repository and its deployment were not modified to publish this repository.

This release organises the product source, selected visuals and separate local-model evidence into one reviewable repository. It does not silently combine the application models with the MedGemma experiment.

## Data and models

| Source | Role | Boundary |
|---|---|---|
| [cBioPortal](https://www.cbioportal.org/) | Four public colorectal cohorts: MSK 2017, MSK 2026, SYSUCC and TCGA | Public de-identified source facts; study-specific terms apply |
| [ClinicalTrials.gov](https://clinicaltrials.gov/data-api/api) | Trial/protocol and site snapshots | Snapshot versions are not a guarantee of current recruitment |
| [TREC Clinical Trials track](https://www.trec-cds.org/) | Synthetic profiles and assessor judgments for research evaluation | Broad medical research cohort; not colorectal clinical ground truth |
| [Google MedGemma 1.5 4B](https://huggingface.co/google/medgemma-1.5-4b-it) | Base medical language model for the separate local experiment | Gated upstream model; original terms apply; base weights not bundled |
| [BGE-M3](https://huggingface.co/BAAI/bge-m3) | Prototype embedding model | Upstream model and terms; not a trained proprietary LANA embedding |

The frozen benchmark row publication includes identifiers, template group, gold class and predictions, but no clinical narratives or raw API responses. It is for post-evaluation metric replay, not an optimisation split.

## Images

The 11 primary images are the team's reviewed publication set: generated cover, selected original high-level/service/inference diagrams, a new logo-led follow-up diagram, unchanged benchmark exports and five unmodified live UI captures. [Asset hashes](../assets/manifest.json), [logo reference sources](../assets/logo-sources.json) and [imagegen prompts](image-prompts/) are retained.

Service marks identify technologies and remain their owners' property. The architecture images depict a proposed deployment, even where the artwork uses present-tense service descriptions. See [implementation status](status.md).
