"""Label definitions sent to the model, derived from schema/labels.md.

Bump PROMPT_VERSION whenever any text here changes: it is part of label_config,
so cached results made under an older version are never reused.
"""

PROMPT_VERSION = "enrich-v1"
LABELS_VERSION = "labels-v1"

TOPICS = {
    "access": "Login, signup, password, account access or recovery.",
    "usability": "Navigation, controls, layout, UI changes, queue/playlist management, ad interruptions "
                 "(not controls locked behind Premium).",
    "playback": "Music won't play, stops, skips, crashes, lag, connection failures, audio quality, battery/data use.",
    "downloads": "Downloading, saved music, offline listening, disappearing downloads.",
    "catalog": "Missing songs/artists, search, discovery, recommendations, lyrics, podcasts as content.",
    "billing": "Price, charges, refunds, subscriptions, paywalls, Premium entitlement, features locked to Premium. "
               "Merely mentioning a paid plan is not billing.",
    "support": "Contacting customer support and the support response.",
    "other": "General praise or criticism with no specific feature, unrelated or meaningless text.",
}
TOPIC_RULES = ("Pick the problem with the highest severity; if tied, the first specific problem mentioned. "
               "For a positive review pick the first specific praised feature; general praise is other. "
               "If the complaint is that a feature requires Premium, choose billing; if a feature fails for "
               "someone entitled to it, choose that feature's topic.")

INTENTS = {
    "cancellation": "Explicitly leaving, uninstalling, cancelling, switching away, or threatening to.",
    "complaint": "Any negative experience, including mixed praise and criticism; generic 'bad app' counts.",
    "request": "Asks for a change without reporting a failure.",
    "praise": "Positive, with no complaint or request.",
    "unclear": "Meaningless, unrelated, or a bare boycott slogan with no product complaint or personal departure.",
}
INTENT_RULES = "Precedence: cancellation, then complaint, then request, then praise, then unclear."

SEVERITY = {
    "1": "No reported problem: praise, neutral/unclear content, or a pure feature request.",
    "2": "Dislike, generic criticism, minor annoyance (e.g. ads annoying), cosmetic issue; no functional loss.",
    "3": "A function is degraded or restricted; some use or a workaround remains.",
    "4": "A core task is clearly blocked, such as cannot log in, cannot play music, offline not working.",
    "5": "Explicit serious financial, privacy or data harm (hacked account, wrong charge, lost data). "
         "Angry words, 'scam', an expensive plan or a crash alone are not enough.",
}
SEVERITY_RULES = "Judge the reported impact, not the tone. Cancellation intent alone does not raise severity."

SENTIMENT_LEVELS = ["Very negative", "Negative", "Neutral or mixed", "Positive", "Very positive"]

QUOTE_QUESTION = ("Which sentence most directly states the main issue: the most severe specific problem "
                  "(first mentioned if tied), or for a positive review the first specific praised feature?")


def shared_rules():
    """One compact object holding every definition; sent once per batched request."""
    return {
        "topic": {"options": TOPICS, "rules": TOPIC_RULES},
        "intent": {"options": INTENTS, "rules": INTENT_RULES},
        "severity": {"options": SEVERITY, "rules": SEVERITY_RULES},
        "sentiment": {"levels": SENTIMENT_LEVELS},
    }
