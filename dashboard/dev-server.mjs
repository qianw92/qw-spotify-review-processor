// Local preview only: serves public/ and routes /api/* to the same handlers Vercel runs.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
// Local only: use the read-only role from the project .env (never the owner role).
if (!process.env.DATABASE_URL) {
  const line = readFileSync(new URL("../.env", import.meta.url), "utf8").split("\n").find((l) => l.startsWith("DATABASE_URL_READONLY="));
  process.env.DATABASE_URL = line.slice("DATABASE_URL_READONLY=".length).trim();
}
const routes = { "/api/summary": "./api/summary.js", "/api/issue": "./api/issue.js", "/api/review": "./api/review.js" };
http.createServer(async (req, res) => {
  const path = new URL(req.url, "http://x").pathname;
  if (routes[path]) return (await import(routes[path])).default(req, res);
  try {
    const body = await readFile(new URL("./public" + (path === "/" ? "/index.html" : path), import.meta.url));
    res.setHeader("Content-Type", path.endsWith(".js") ? "text/javascript" : "text/html; charset=utf-8");
    res.end(body);
  } catch { res.statusCode = 404; res.end("not found"); }
}).listen(process.env.PORT || 3005, () => console.log("dashboard on http://localhost:" + (process.env.PORT || 3005)));
