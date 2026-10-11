"""Stage 4 — Group (role: group).

Code assigns every completed complaint/cancellation record to exactly one issue using the fixed rules in
schema/issues.json (topic + entities). Issue IDs and membership never depend on a model, so ranking can be
rebuilt from saved files. A small model only *names* each issue from a bounded evidence pack; if naming
fails, a deterministic fallback name is used and recorded.
"""
import csv
import json
from pathlib import Path

from . import llm

ROOT = Path(__file__).resolve().parent.parent
ISSUES = json.loads((ROOT / "schema" / "issues.json").read_text())
PROMPT_VERSION = "group-names-v1"
EXAMPLES_PER_ISSUE = 4
EXAMPLE_CHARS = 160

SCHEMA = """
DROP TABLE IF EXISTS membership;
CREATE TABLE membership (issue_id TEXT NOT NULL, review_id TEXT NOT NULL, PRIMARY KEY (issue_id, review_id));
DROP TABLE IF EXISTS issues;
CREATE TABLE issues (issue_id TEXT PRIMARY KEY, topic TEXT, rule_key TEXT, name TEXT, description TEXT,
                     name_source TEXT, members INTEGER);
"""

INSTRUCTIONS = ("You name customer-complaint issues for a product team. For every issue in `issues`, write a short "
                "name (max 8 words) and a one-sentence description based only on its topic, rule and example "
                "complaints. Do not invent counts, causes or customer facts. Return every issue_id exactly once "
                "and no others.")


def assign(topic, entities):
    for rule in ISSUES["rules"].get(topic, []):
        if any(e in entities for e in rule["entities"]):
            return f"ISS-{topic}-{rule['key']}", rule["key"]
    return f"ISS-{topic}-general", "general"


def fallback_name(topic, key):
    return f"{topic.capitalize()}: {key.replace('_', ' ')}" if key != "general" else f"{topic.capitalize()}: general complaints"


def run(con, run_dir, guard, phase="initial"):
    con.executescript(SCHEMA)
    rows = con.execute("""SELECT l.review_id, l.topic, l.entities, l.severity, l.evidence_quote, l.cache_source_id,
                                 r.row_index
                          FROM labels l JOIN records s USING (review_id) JOIN reviews r USING (review_id)
                          WHERE s.status='completed' AND l.intent IN ('complaint','cancellation')""").fetchall()
    issues = {}
    with con:
        for rid, topic, ents, sev, quote, cache_src, row_index in rows:
            iid, key = assign(topic, json.loads(ents))
            con.execute("INSERT INTO membership VALUES (?,?)", (iid, rid))
            it = issues.setdefault(iid, {"topic": topic, "rule_key": key, "members": 0, "examples": []})
            it["members"] += 1
            if cache_src is None:  # examples come from distinct texts only
                it["examples"].append((-sev, row_index, rid, quote))

    pack = []
    for iid in sorted(issues):
        it = issues[iid]
        ex = sorted(it["examples"])[:EXAMPLES_PER_ISSUE]  # most severe first, then earliest; deterministic
        it["example_ids"] = [e[2] for e in ex]
        pack.append({"issue_id": iid, "topic": it["topic"], "rule": it["rule_key"],
                     "examples": [{"review_id": e[2], "text": e[3][:EXAMPLE_CHARS]} for e in ex]})

    names, info = {}, {"cached": False, "model_used": False}
    if pack:
        want = {p["issue_id"] for p in pack}

        def validate(out):
            got = [x["issue_id"] for x in out.get("issues", [])]
            probs = []
            if set(got) != want or len(got) != len(want):
                probs.append(f"issue_ids must be exactly {sorted(want)}")
            probs += [f"name too long for {x['issue_id']}" for x in out.get("issues", []) if len(x["name"]) > 70]
            return probs

        schema = {"type": "object", "additionalProperties": False, "required": ["issues"],
                  "properties": {"issues": {"type": "array", "items": {
                      "type": "object", "additionalProperties": False, "required": ["issue_id", "name", "description"],
                      "properties": {"issue_id": {"type": "string"}, "name": {"type": "string"},
                                     "description": {"type": "string"}}}}}}
        sent_ids = sorted({e["review_id"] for p in pack for e in p["examples"]})
        try:
            out, info = llm.call_json(con=con, run_dir=run_dir, guard=guard, role="group",
                                      prompt_version=PROMPT_VERSION, instructions=INSTRUCTIONS,
                                      payload={"issues": pack}, schema=schema, schema_name="issue_names",
                                      max_output_tokens=60 * len(pack) + 200, review_ids=sent_ids,
                                      validate=validate, phase=phase)
            names = {x["issue_id"]: (x["name"], x["description"]) for x in out["issues"]}
            info["model_used"] = True
        except llm.LLMFailed as e:
            info = {"model_used": False, "fallback_reason": str(e)}

    out_dir = Path(run_dir)
    with con:
        for iid, it in issues.items():
            name, desc = names.get(iid, (fallback_name(it["topic"], it["rule_key"]), ""))
            con.execute("INSERT INTO issues VALUES (?,?,?,?,?,?,?)",
                        (iid, it["topic"], it["rule_key"], name, desc, "model" if iid in names else "fallback",
                         it["members"]))
    with open(out_dir / "issues.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["issue_id", "topic", "rule_key", "name", "description", "name_source", "members",
                    "example_review_ids"])
        for iid in sorted(issues):
            it = issues[iid]
            name, desc = names.get(iid, (fallback_name(it["topic"], it["rule_key"]), ""))
            w.writerow([iid, it["topic"], it["rule_key"], name, desc, "model" if iid in names else "fallback",
                        it["members"], " ".join(it["example_ids"])])
    with open(out_dir / "membership.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["issue_id", "review_id"])
        w.writerows(con.execute("SELECT issue_id, review_id FROM membership ORDER BY issue_id, review_id"))
    return {"complaint_records": len(rows), "issues": len(issues), "naming": info,
            "named_by_model": len(names), "fallback_named": len(issues) - len(names)}
