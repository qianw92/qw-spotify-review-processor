// GET /api/review?id=<review_id> — full trace for one review: source fields -> labels -> issue -> rank.
import { query, send } from "../lib/db.js";

export default async function handler(req, res) {
  const id = new URL(req.url, "http://x").searchParams.get("id") || "";
  if (!/^[0-9a-f-]{36}$/.test(id)) return send(res, 400, { error: "bad review id" });
  try {
    const rows = await query(`SELECT r.review_id, r.row_index, r.status, r.reason, r.review_text, r.review_rating,
                                     to_char(r.review_timestamp, 'YYYY-MM-DD HH24:MI') AS review_timestamp, r.app_version,
                                     r.topic, r.intent, r.severity, r.sentiment, r.needs_review, r.evidence_quote,
                                     r.cache_source_id, r.label_config, r.issue_id, i.name AS issue_name, i.rank AS issue_rank
                              FROM reviews_processed r LEFT JOIN issues i USING (issue_id)
                              WHERE r.review_id = $1`, [id]);
    if (!rows.length) return send(res, 404, { error: "unknown review" });
    send(res, 200, rows[0]);
  } catch (e) {
    send(res, 500, { error: "database query failed" });
  }
}
