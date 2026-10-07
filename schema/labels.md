# Label Rulebook — v1

The shared definitions every review is labeled against. They follow `GRADING_CONTRACT.md` exactly; the examples and boundary rules below are ours.

- **Label config:** `labels-v1` (any change to this file bumps the version, which invalidates cached results)
- **Input:** `review_text` only. Star rating, likes, app version and date are **never** used to choose a label.
- **Examples:** real reviews from the development set `analysis_10000.csv` (ID prefix shown). None come from the golden 50.

---

## 1. Topic — what the review is about (pick exactly one)

| Topic | Covers | Does **not** cover |
|---|---|---|
| `access` | Login, signup, password, account access, account recovery | Support contact about a login problem (still `access` unless the complaint is about support itself) |
| `usability` | Navigation, controls, layout, UI changes, queue/playlist management, **ad interruptions** | Controls that are locked behind Premium (→ `billing`) |
| `playback` | Won't play, stops, skips, crashes, lag, connection failures, audio quality, battery/data use | Offline/downloaded music failing (→ `downloads`) |
| `downloads` | Downloading, saved music, offline listening, disappearing downloads | Complaints that offline mode requires paying (→ `billing`) |
| `catalog` | Missing songs/artists, search, discovery, recommendations, lyrics, podcasts as content | Lyrics/features locked behind Premium (→ `billing`) |
| `billing` | Price, charges, refunds, subscriptions, paywalls, Premium entitlement, **features explicitly locked to Premium** | A Premium user's unrelated bug (a paying user's crash is `playback`) |
| `support` | Contacting support and the quality of the response | — |
| `other` | General praise or criticism with no specific feature, unrelated or meaningless text | — |

### Tie-break rules (from the contract)
1. Several problems → choose the one with the **highest severity**; if tied, the **first specific problem mentioned**.
2. Positive review → the **first specific praised feature**; general praise ("Good", "Love it") is `other`.
3. **Mentioning a paid plan is not enough for `billing`.** A subscription that won't activate is `billing`; music crashing for a paying customer is `playback`.
4. **Paywall rule (ours):** if the complaint is *that a feature requires Premium*, the topic is `billing`. If the feature *fails* for someone entitled to it, use that feature's topic.

### Topic examples

| Review (dev set) | Topic | Why |
|---|---|---|
| `1cc0b5bd` "Won't let me log in. Tried resetting password but still won't let me log in." | `access` | Can't get into the account |
| `84acb6b0` "Login problems faced many times. Every time demanding new contact number." | `access` | "contact" is about a phone number, not support |
| `04573fd8` "this is good but ads are annoying" | `usability` | Ad interruptions are usability |
| `17d2189a` "This new main page UI is terrible" | `usability` | Layout/UI |
| `332d89b4` "Weirdly stops playing every handful of minutes." | `playback` | Playback stops |
| `ac7b9d5f` "Podcast keeps playing when ads are playing after update" | `playback` | Audio playback bug, even though "podcast" sounds like catalog |
| `5446716b` "I just bought premium again… it just skips library everytime I scroll" | `usability` | Paid plan mentioned, but the problem is navigation |
| `3569509e` "Offline mode does not work at all. All my playlists are missing." | `downloads` | Offline listening fails |
| `b9e5a33f` "…doesn't load lyrics most of the time…" | `catalog` | Lyrics availability |
| `4e794d28` "It's good but doesn't play offline unless you pay for a subscription" | `billing` | Paywall rule: the complaint is that offline needs Premium |
| `db73c4f7` "For free users… no queue, no repeat, no way to go to previous song" | `billing` | Premium-only controls go to billing (contract) |
| `2de6923d` "Works well and customer service is great" | `support` | First specific praised feature is support |
| `713a00d8` "Love Spotify. It so easy to program all your favorite songs…" | `usability` | First specific praised feature: playlist building |
| "Good" (12,845 copies) | `other` | General praise |

---

## 2. Intent — what the reviewer is doing (precedence order)

Check top to bottom; take the **first** that applies.

| Order | Intent | Definition | Example |
|---|---|---|---|
| 1 | `cancellation` | Explicitly leaving, uninstalling, cancelling, switching away, or threatening to | `71dd9d34` "The update sucks. To many ads. Going to uninstall it." |
| 2 | `complaint` | Any negative experience, including mixed praise + criticism; generic "bad app" counts | `04573fd8` "this is good but ads are annoying" |
| 3 | `request` | Asks for a change without reporting a failure | `1f41e81e` "An 'autoplay when connecting to bluetooth' feature would be nice" |
| 4 | `praise` | Positive with no complaint or request | `d15761ac` "Great selection of podcasts & I love i can search…" |
| 5 | `unclear` | Meaningless, unrelated, or a bare boycott slogan with no product complaint or personal departure | "." / an unrelated political slogan |

**Notes**
- "Bad app" / "Worst app" → `complaint` (topic `other`). Do not invent a specific defect.
- A resolved problem praised afterwards (`39987350` "having problem with logging but Spotify team contact asap!! great response") → `praise`, topic `support`; flagged `needs_review` as ambiguous.
- Non-English text is classified when the meaning is clear (e.g. `eb748acc`, Indonesian: horror ads at night, "uninstalled" → `cancellation`, `usability`). If meaning is unclear → `unclear` + `needs_review`.

---

## 3. Severity — how bad the reported impact is (integer 1–5)

Judge **the reported impact**, not the tone. Stars, angry words, "scam", or cancellation intent **alone never raise severity**.

| Level | Meaning | Example (dev set) |
|---|---|---|
| **1** | No reported problem: praise, neutral/unclear, or a pure feature request | `2c2fefc7` "Always great! Even the support team is amazing!" · `c6eca5eb` "improve the shuffle feature" |
| **2** | Dislike, generic criticism, minor annoyance, cosmetic issue; no functional loss | `04573fd8` "ads are annoying" · `17d2189a` "new main page UI is terrible" · "Worst app" |
| **3** | A function is degraded or restricted, but some use or a workaround remains | `332d89b4` "stops playing every handful of minutes" · `b9e5a33f` "doesn't load lyrics most of the time" · `db73c4f7` free users lose queue/repeat |
| **4** | A core task is clearly blocked (can't log in, can't play music, offline doesn't work) | `1cc0b5bd` "Won't let me log in… still won't let me log in" · `3569509e` "Offline mode does not work at all" |
| **5** | **Explicit** serious financial, privacy or data harm | `305c3fe1` "Unable to login… Looks like the account was hacked." · `d87536c5` "hacked, can't even recover the playlists… cost over three hundred dollars" |

**Boundary rules (ours)**
- "Scam" / "fraud" used as an insult about Premium pricing (`38347238`, `3b31acda`) is **not** level 5 — no explicit harm. Usually 2–3.
- Unexpected or double charges, refused refunds, a hacked account, or permanently lost user data → 5.
- Missing context ("doesn't work") → choose the lower supported level and set `needs_review`.

---

## 4. Sentiment — overall tone (number −1 to 1)

Scored on 5 levels, then mapped: `sentiment = level / 2 − 1`.

| Level | Meaning | Value |
|---|---|---|
| 0 | Very negative | −1.0 |
| 1 | Negative | −0.5 |
| 2 | Neutral or mixed | 0.0 |
| 3 | Positive | 0.5 |
| 4 | Very positive | 1.0 |

Jev may return a fractional level (e.g. 1.4 → −0.3); we keep it, rounded to 2 decimals. Golden-set check: mean absolute error, with a predeclared tolerance of **±0.5**.

---

## 5. Entities — features named in the text (list of strings)

Extracted **by code**, not the model: case-insensitive whole-word match against a fixed vocabulary (`schema/entities.json`, e.g. `premium`, `ads`, `shuffle`, `lyrics`, `podcast`, `offline`, `download`, `playlist`, `login`, `bluetooth`). Only terms literally present in the review are listed, so the list can never contain unsupported additions. Empty list is valid.

---

## 6. Evidence quote — exact words that support the label

Must be an **exact substring** of the original `review_text` (checked by code).

- Review ≤ 200 characters → the whole text is the quote.
- Longer review → split into sentences by code; the model picks the sentence that best supports the chosen topic. Code verifies it is an exact substring.

---

## 7. needs_review — flag for human attention (true/false)

Set to `true` when any of these hold:
- Model confidence on topic, intent or severity is below a threshold (tuned on development data, not the golden set)
- Meaning unclear, mostly non-English with uncertain meaning, or missing context for severity
- The selected quote may not support the label

`needs_review` is a prediction; we evaluate it on the golden set rather than treating it as a guarantee.
