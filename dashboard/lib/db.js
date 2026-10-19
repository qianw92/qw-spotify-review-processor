// One pooled, read-only connection shared by every API route.
// DATABASE_URL must be the dashboard_reader role (SELECT only, read-only transactions).
import pg from "pg";
import { attachDatabasePool } from "@vercel/functions";

const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL, max: 5 });
try { attachDatabasePool(pool); } catch { /* not on Vercel (local dev server) */ }

export async function query(sql, params = []) {
  const { rows } = await pool.query(sql, params);
  return rows;
}

export function send(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "public, max-age=300, s-maxage=3600");
  res.end(JSON.stringify(body));
}
