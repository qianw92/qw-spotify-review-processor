// GET /api/issue?id=ISS-... — issue detail plus a reproducible sample of member reviews.
import { query, send } from "../lib/db.js";

export default async function handler(req, res) {
  const id = new URL(req.url, "http://x").searchParams.get("id") || "";
  if (!/^ISS-[a-z_]+-[a-z_]+$/.test(id)) return send(res, 400, { error: "bad issue id" });
  try {
    const issue = await query(`SELECT issue_id, rank, topic, area, name, description, complaint_count, severity_sum,
                                      mean_severity::text AS mean_severity, priority_score, cancellation_count,
                                      severity_mix FROM issues WHERE issue_id = $1`, [id]);
    if (!issue.length) return send(res, 404, { error: "unknown issue" });
    // Distinct texts only (no duplicate copies), deterministic pseudo-random order.
    const reviews = await query(`SELECT review_id, severity, intent, sentiment, review_rating,
                                        to_char(review_timestamp, 'YYYY-MM-DD') AS date, evidence_quote
                                 FROM reviews_processed
                                 WHERE issue_id = $1 AND cache_source_id IS NULL
                                 ORDER BY md5(review_id) LIMIT 12`, [id]);
    send(res, 200, { issue: issue[0], sample_reviews: reviews });
  } catch (e) {
    send(res, 500, { error: "database query failed" });
  }
}
