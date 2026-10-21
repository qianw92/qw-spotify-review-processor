# Verifier prompt (verify-v1, Jev)

*Exported from the code by `python -c` (see README); the code is the source of truth.*

**Model:** `jev-1.13.0` · independent of the enricher: sees only the text and the same taxonomy, with different question wording and reversed option order, never the first labels.

- topic: "Audit `texts.vNN`: which category in `taxonomy.topic` does it mainly concern? Apply the taxonomy's rules."
- intent: "Audit `texts.vNN`: what is the writer doing, per `taxonomy.intent` and its precedence?"
- severity: "Audit `texts.vNN`: how serious is the reported impact, per `taxonomy.severity`?"
- sentiment: "Audit `texts.vNN`: overall tone."
