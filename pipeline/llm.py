"""OpenAI calls for language-generation roles (group naming, memo writing).

Every call: structured JSON output (strict schema), reasoning effort none, capped output tokens,
spend reservation before dispatch, one retry for invalid/incomplete output, bounded backoff for
transient API errors, every attempt logged, and an exact-request cache so a warm rerun makes no call.
"""
import datetime
import hashlib
import json
import random
import time

from . import budget, calllog

PROVIDER = "openai"
MODEL = "gpt-6-luna"
REASONING_EFFORT = "none"
CHARS_PER_TOKEN_ESTIMATE = 3.0
API_ATTEMPTS = 3
INVALID_OUTPUT_ATTEMPTS = 2  # first try + one retry


class LLMFailed(RuntimeError):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def call_json(*, con, run_dir, guard, role, prompt_version, instructions, payload, schema, schema_name,
              max_output_tokens, review_ids=(), validate=None, phase="initial"):
    """Returns (parsed_json, info). validate(parsed) -> list of problems (empty = accept)."""
    from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

    user_input = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256(json.dumps([MODEL, REASONING_EFFORT, prompt_version, instructions, user_input, schema],
                                    sort_keys=True).encode()).hexdigest()
    hit = con.execute("SELECT response, request_id FROM llm_cache WHERE cache_key=?", (key,)).fetchone()
    if hit:
        return json.loads(hit[0]), {"cached": True, "request_id": hit[1], "cache_key": key}

    est_in = int((len(instructions) + len(user_input) + len(json.dumps(schema))) / CHARS_PER_TOKEN_ESTIMATE)
    reservation = budget.cost(PROVIDER, est_in, max_output_tokens)  # worst case: every output token used
    client = OpenAI(max_retries=0, timeout=120)
    feedback = None
    for content_attempt in range(1, INVALID_OUTPUT_ATTEMPTS + 1):
        guard.check(reservation)
        text_input = user_input if feedback is None else user_input + "\n\nYOUR PREVIOUS ANSWER WAS REJECTED: " + feedback
        resp = None
        for api_attempt in range(1, API_ATTEMPTS + 1):
            started = time.time()
            try:
                resp = client.responses.create(
                    model=MODEL, instructions=instructions, input=text_input,
                    reasoning={"effort": REASONING_EFFORT}, max_output_tokens=max_output_tokens,
                    text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}})
                break
            except (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError) as e:
                calllog.log_call(run_dir, role=role, model=MODEL, phase=phase, outcome="failed",
                                 request_id=f"local-{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                                 review_ids=list(review_ids), input_tokens=0, output_tokens=0,
                                 prompt_version=prompt_version, attempt=api_attempt,
                                 error=f"{type(e).__name__}: {str(e)[:200]}", seconds=round(time.time() - started, 3))
                if isinstance(e, APIStatusError) and not isinstance(e, RateLimitError) and e.status_code < 500:
                    raise LLMFailed(f"{role}: non-retryable API error {e.status_code}") from e
                if api_attempt == API_ATTEMPTS:
                    raise LLMFailed(f"{role}: API failed {API_ATTEMPTS} times") from e
                time.sleep(min(8, 0.5 * 2 ** api_attempt) + random.uniform(0, 0.5))

        u = resp.usage
        tin, tout = u.input_tokens, u.output_tokens  # output_tokens already includes any reasoning tokens
        cached_in = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
        usd = budget.record(PROVIDER, resp.model, role, resp.id, tin, tout)
        guard.add(usd)
        problems = []
        parsed = None
        if resp.status != "completed":
            problems.append(f"response status {resp.status}")
        else:
            try:
                parsed = json.loads(resp.output_text)
                problems = validate(parsed) if validate else []
            except json.JSONDecodeError as e:
                problems.append(f"invalid JSON: {e}")
        outcome = "succeeded" if not problems else "failed"
        calllog.log_call(run_dir, role=role, model=resp.model, phase=phase, outcome=outcome, request_id=resp.id,
                         review_ids=list(review_ids), input_tokens=tin, output_tokens=tout,
                         cached_input_tokens=cached_in, reasoning_effort=REASONING_EFFORT,
                         prompt_version=prompt_version, attempt=content_attempt, cost_usd=round(usd, 8),
                         seconds=round(time.time() - started, 3),
                         **({"validation_problems": problems[:10]} if problems else {}))
        if not problems:
            con.execute("INSERT OR REPLACE INTO llm_cache VALUES (?,?,?,?,?)",
                        (key, role, json.dumps(parsed, ensure_ascii=False), resp.id, _now()))
            con.commit()
            return parsed, {"cached": False, "request_id": resp.id, "cache_key": key,
                            "input_tokens": tin, "output_tokens": tout, "attempts": content_attempt}
        feedback = "; ".join(problems[:10])
    raise LLMFailed(f"{role}: output rejected after {INVALID_OUTPUT_ATTEMPTS} attempts: {feedback}")
