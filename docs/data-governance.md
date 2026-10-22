# Hospital control and data boundaries

**Data sovereignty is a deployment objective, not a certification supplied by local inference.** Each participating hospital is intended to retain custody of patient information and authority over its permitted uses and disclosures.

## Target boundary

Patient records, embeddings, model inference, outcome evidence and audit logs stay within the authorised hospital environment. Public trial snapshots enter a local catalogue. Patient-scoped retrieval and purpose-limited tools constrain what a matching request can access.

Clinical referrals and Sponsor feasibility have different disclosure paths:

- A treating team reviews a minimum referral packet before authorised release to a Trial Site.
- Sponsors/CROs receive only hospital-approved aggregates through a governed disclosure process.

IRIS can provide an integration/data foundation for authorised participating hospitals. It does not itself grant access to every hospital, reconcile identities across hospitals, or approve external disclosure.

## What this release demonstrates

The static demo uses public de-identified source data and a labelled simulated overlay. The separate local-model benchmark uses public synthetic profiles. Public-data API baseline requests do not establish that private hospital records can be sent to those services.

No live hospital data custody, EHR connection, cross-hospital identity resolution, regulatory compliance or full-platform sovereignty certification was validated here. Such evidence needs the actual deployment configuration, authorisations and operational review.

## Feedback data

Outcome collection does not automatically authorise training or cross-hospital weight sharing. A future outcome-learning study needs a defined purpose, action, reward, observation window, authorised data use and held-out evaluation. Missing follow-up and patient/site decisions must remain visible rather than being converted into convenient training labels.
