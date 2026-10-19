// GET /api/summary — everything the overview needs, read from the database (no model calls).
import { query, send } from "../lib/db.js";

export default async function handler(req, res) {
  try {
    const [metrics, areas, issues, dist, rec, claims] = await Promise.all([
      query("SELECT key, value FROM metrics"),
      query("SELECT * FROM areas ORDER BY severity_sum DESC"),
      query(`SELECT issue_id, rank, topic, area, name, description, complaint_count, severity_sum,
                    mean_severity::text AS mean_severity, priority_score, cancellation_count,
                    share_of_complaints_pct::float AS share_pct, severity_mix
             FROM issues ORDER BY rank`),
      query("SELECT dimension, bucket, records, complaints FROM distributions"),
      query("SELECT recommended_area, headline, memo_markdown, cited_reviews, check_result, model, prompt_version FROM recommendation"),
      query("SELECT claim_id, issue_id, metric, value FROM claims ORDER BY length(claim_id), claim_id"),
    ]);
    send(res, 200, {
      metrics: Object.fromEntries(metrics.map((m) => [m.key, m.value])),
      areas, issues, distributions: dist, recommendation: rec[0], claims,
    });
  } catch (e) {
    send(res, 500, { error: "database query failed" });
  }
}
