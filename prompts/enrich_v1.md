# Enricher prompt (enrich-v1, Jev)

*Exported from the code by `python -c` (see README); the code is the source of truth.*

**Model:** `jev-1.13.0` · **label_config:** `jev-1.13.0+enrich-v1+labels-v1+batched` · up to 50 reviews per request.

Each request sends the shared rules once in `state.label_rules` and four questions per review (topic Choice, intent Choice, severity Choice, sentiment Score) plus, for reviews over 200 characters, a quote Choice over the review's sentences.

## Shared rules (`state.label_rules`)

```json
{
  "topic": {
    "options": {
      "access": "Login, signup, password, account access or recovery.",
      "usability": "Navigation, controls, layout, UI changes, queue/playlist management, ad interruptions (not controls locked behind Premium).",
      "playback": "Music won't play, stops, skips, crashes, lag, connection failures, audio quality, battery/data use.",
      "downloads": "Downloading, saved music, offline listening, disappearing downloads.",
      "catalog": "Missing songs/artists, search, discovery, recommendations, lyrics, podcasts as content.",
      "billing": "Price, charges, refunds, subscriptions, paywalls, Premium entitlement, features locked to Premium. Merely mentioning a paid plan is not billing.",
      "support": "Contacting customer support and the support response.",
      "other": "General praise or criticism with no specific feature, unrelated or meaningless text."
    },
    "rules": "Pick the problem with the highest severity; if tied, the first specific problem mentioned. For a positive review pick the first specific praised feature; general praise is other. If the complaint is that a feature requires Premium, choose billing; if a feature fails for someone entitled to it, choose that feature's topic."
  },
  "intent": {
    "options": {
      "cancellation": "Explicitly leaving, uninstalling, cancelling, switching away, or threatening to.",
      "complaint": "Any negative experience, including mixed praise and criticism; generic 'bad app' counts.",
      "request": "Asks for a change without reporting a failure.",
      "praise": "Positive, with no complaint or request.",
      "unclear": "Meaningless, unrelated, or a bare boycott slogan with no product complaint or personal departure."
    },
    "rules": "Precedence: cancellation, then complaint, then request, then praise, then unclear."
  },
  "severity": {
    "options": {
      "1": "No reported problem: praise, neutral/unclear content, or a pure feature request.",
      "2": "Dislike, generic criticism, minor annoyance (e.g. ads annoying), cosmetic issue; no functional loss.",
      "3": "A function is degraded or restricted; some use or a workaround remains.",
      "4": "A core task is clearly blocked, such as cannot log in, cannot play music, offline not working.",
      "5": "Explicit serious financial, privacy or data harm (hacked account, wrong charge, lost data). Angry words, 'scam', an expensive plan or a crash alone are not enough."
    },
    "rules": "Judge the reported impact, not the tone. Cancellation intent alone does not raise severity."
  },
  "sentiment": {
    "levels": [
      "Very negative",
      "Negative",
      "Neutral or mixed",
      "Positive",
      "Very positive"
    ]
  }
}
```

## Per-review questions

- topic: "Primary topic of review `reviews.rNN`, using `label_rules.topic`."
- intent: "Intent of review `reviews.rNN`, using `label_rules.intent`."
- severity: "Severity of review `reviews.rNN`, using `label_rules.severity`."
- sentiment (Score, 5 levels ['Very negative', 'Negative', 'Neutral or mixed', 'Positive', 'Very positive']): "Overall sentiment of review `reviews.rNN`."
- quote (long reviews only): "For review `reviews.rNN`: Which sentence most directly states the main issue: the most severe specific problem (first mentioned if tied), or for a positive review the first specific praised feature?"
