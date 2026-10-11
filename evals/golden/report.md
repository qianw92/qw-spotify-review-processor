# Golden-50 evaluation

**Setup.** 50 reviews hand-labeled by the project author *before* any model saw them (`golden_50_labeled.csv`;
4 marked ambiguous). Jev (`jev-1.13.0+enrich-v1+labels-v1+batched`) labeled the review **text only** in one
request; human labels were read afterwards by code. The golden set was never used to tune prompts, examples or
thresholds. Missing predictions would count as wrong (there were none). Cost: $0.00065.

*Disclosure:* after hand-labeling, the author asked the coding assistant to check the labels for consistency with
the written rulebook; the assistant listed possible rule conflicts and the author made every final call.

## Results

| Field | Result |
|---|---|
| Topic agreement (also-acceptable topic counts) | **88%** (44/50) |
| Intent agreement | **92%** (46/50) |
| Severity exact / mean absolute error | **76%** (38/50) / **0.28** levels |
| All three correct | 68% (34/50) |
| Sentiment MAE / within predeclared ±0.5 | 0.22 / **96%** |
| Evidence quote is an exact substring (code check) | 50/50 |
| Quote identical to the human's chosen quote | 47/50 |
| Unsupported entities | 0 (entities are literal word matches by construction) |
| `needs_review` flagged | 12 — precision 58% / recall 44% against "any field wrong" |

50 cases is a small diagnostic sample, not a precise population accuracy estimate.

## Confusion (human → model)

**Severity:** 1→1 ×27, 1→2 ×2 · 2→2 ×8, 2→3 ×4, 2→5 ×1 · 3→3 ×1, 3→4 ×4 · 4→4 ×2, 4→3 ×1
**Intent:** unclear→unclear ×4, unclear→complaint ×2, unclear→request ×1 · praise→praise ×20, praise→complaint ×1 ·
complaint, request, cancellation all 100%

## Error analysis

1. **Severity runs one level high (main pattern).** 11 of 12 severity errors are the model choosing a *higher* level,
   mostly 2→3 and 3→4: "plays a little bit then it stops" (#11), "unable to play in offline mode" (#45), "everything
   basic features is premium" (#30). The model reads "degraded" as "blocked". One large miss: #33 (sudden loud ad,
   "dangerous… my ears explode") 2→5 — the model treated a physical-discomfort complaint as serious harm.
   *Effect on results:* priority scores are inflated roughly uniformly, so issue order is more reliable than absolute
   severity values; reported as a limitation.
2. **Boycott / hate text read as complaints.** #1, #31 (political or religious boycott with no product complaint) →
   the human said `unclear`, the model said `complaint`. These carry severity 1–2 and land in `ISS-other-general`,
   so they inflate the generic bucket, not a product area.
3. **Topic boundary cases.** #10 "Duo Premium… No ads" (usability vs billing), #29 free-tier control limits
   (billing paywall rule vs usability), #43 "can't play the songs… can't rewind" (usability vs playback),
   #44 "finds and plays whatever music… adds songs you might like" (usability vs catalog). All are defensible
   alternatives under the rulebook; only #29 conflicts with an explicit rule (paywall → billing).
4. **Non-English.** #17 Tagalog "all the songs are on Spotify" read as a catalog complaint (human: praise). #19
   Indonesian lyrics complaint was correct on topic and intent, one level high on severity.
5. **`needs_review` is a weak signal.** It caught 7 of 16 wrong cases; confidence alone does not identify most errors.

## Handling decisions

- No prompt was changed after seeing these results (changing it would require a fresh held-out set).
- The severity bias and boycott handling are documented as limitations; the memo uses area-level comparisons and
  counts of severity 4–5 complaints alongside the baseline score.
