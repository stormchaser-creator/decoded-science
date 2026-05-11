/**
 * Decoded PM2 Ecosystem Config
 *
 * Processes:
 *   decoded-api      — FastAPI + uvicorn (REST API + Pearl connectome)
 *   decoded-extract  — Paper extraction worker (Claude Haiku)
 *   decoded-graph    — Neo4j graph sync worker (batch, runs on interval)
 *   decoded-connect  — Connection discovery worker (graph + LLM)
 *   decoded-critique — Paper critique worker (Claude Sonnet)
 *   decoded-outreach — Author outreach processor (generates emails from high-confidence connections)
 *   decoded-explorer — Vite React frontend (served by nginx in prod)
 *
 * Start:  pm2 start ecosystem.config.js
 * Stop:   pm2 stop decoded-api
 * Logs:   pm2 logs decoded-api
 * Save:   pm2 save
 *
 * 2026-05-10 — templatized for Mac Mini → Mac Studio migration. All paths now
 * derived from __dirname (path of this config file), so the same config works
 * on either machine without env vars or hardcoded /Users/whit references.
 *
 * DATABASE_URL / NEO4J_URI / REDIS_URL still resolve via .env (loaded below).
 * Studio's Decoded checkout will need its own .env with DATABASE_URL pointing
 * at Studio's Postgres when Decoded is migrated (Phase 9 of the main plan).
 */

const fs = require("fs");
const path = require("path");

// HOME = path to this Decoded checkout. __dirname is the dir of this config
// file, which is always the project root regardless of machine.
const HOME = __dirname;
const VENV_PY = path.join(HOME, ".venv", "bin", "python");
const VENV_UVICORN = path.join(HOME, ".venv", "bin", "uvicorn");
const LOGS = path.join(HOME, "logs");

// Read secrets from .env at config load time (file is gitignored)
const _env = {};
try {
  fs.readFileSync(path.join(HOME, ".env"), "utf8")
    .split("\n")
    .forEach((line) => {
      const m = line.match(/^([^#=\s][^=]*)=(.*)$/);
      if (m) _env[m[1].trim()] = m[2].trim();
    });
} catch (_) {}

// Default connection strings — overridden by .env if present.
// On Mini, localhost resolves to Mini (correct). On Studio, Studio's checkout
// MUST set DATABASE_URL/NEO4J_URI in .env to point at the right host before
// Decoded starts (otherwise it'd hit Studio's empty local Postgres).
const DATABASE_URL =
  _env.DATABASE_URL || "postgresql://whit@localhost:5432/encoded_human";
const NEO4J_URI = _env.NEO4J_URI || "bolt://localhost:7687";
const REDIS_URL = _env.REDIS_URL || "redis://localhost:6379/0";

module.exports = {
  apps: [
    {
      name: "decoded-api",
      cwd: HOME,
      script: VENV_UVICORN,
      args: "decoded.api.main:app --host 0.0.0.0 --port 8000 --workers 2",
      interpreter: "none",
      env: {
        PYTHONPATH: HOME,
        DATABASE_URL,
        NEO4J_URI,
        NEO4J_USER: "neo4j",
        NEO4J_PASSWORD: _env.NEO4J_PASSWORD || "",
        REDIS_URL,
        DECODED_JWT_SECRET: _env.DECODED_JWT_SECRET || "",
        DECODED_API_URL: "https://connectome.theencodedhuman.com",
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      min_uptime: "10s",
      watch: false,
      max_memory_restart: "1G",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: path.join(LOGS, "api-out.log"),
      error_file: path.join(LOGS, "api-error.log"),
      merge_logs: true,
    },
    {
      name: "decoded-extract",
      cwd: HOME,
      script: VENV_PY,
      // Paced throughput: 3 concurrent, 50/batch, $20/day budget (throttled 2026-04-20).
      // Prior $50/day assumed ~$0.011/call, but real cost runs ~$0.015/call → $0.74/batch.
      // At $50 that was ~$37/day actual (observed 2026-04-20: today_usd=37.73).
      // $20/day × 1/$0.74 batch = ~27 batches/day. With 15-min restart_delay that's
      // ~6.75h active work → sleeps on DECODE_EMPTY_BACKOFF for the rest.
      args: "-m decoded.extract.worker --limit 50 --concurrency 3 --daily-budget 20 --total-budget 20",
      interpreter: "none",
      env: {
        PYTHONPATH: HOME,
        DATABASE_URL,
        NEO4J_URI,
        NEO4J_USER: "neo4j",
        NEO4J_PASSWORD: _env.NEO4J_PASSWORD || "",
        REDIS_URL,
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || "",
        DECODE_EMPTY_BACKOFF: "3600", // sleep 1 hour when budget/queue empty
        DECODE_ERROR_BACKOFF: "120",
      },
      autorestart: true, // continuously process — budget check prevents tight loops
      max_restarts: 500,
      restart_delay: 900000, // 15 min between batches — paces $50/day over ~30 hours
      min_uptime: "10s",
      watch: false,
      max_memory_restart: "2G",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: path.join(LOGS, "extract-out.log"),
      error_file: path.join(LOGS, "extract-error.log"),
      merge_logs: true,
    },
    {
      name: "decoded-graph",
      cwd: HOME,
      script: VENV_PY,
      args: "-m decoded.graph.worker --limit 500",
      interpreter: "none",
      env: {
        PYTHONPATH: HOME,
        DATABASE_URL,
        NEO4J_URI,
        NEO4J_USER: "neo4j",
        NEO4J_PASSWORD: _env.NEO4J_PASSWORD || "",
        // Worker sleeps this many seconds when nothing to process, before exit
        DECODE_GRAPH_BACKOFF: "300",
      },
      autorestart: true,
      max_restarts: 100,
      restart_delay: 10000,
      min_uptime: "30s",
      exp_backoff_restart_delay: 100,
      watch: false,
      max_memory_restart: "2G",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: path.join(LOGS, "graph-out.log"),
      error_file: path.join(LOGS, "graph-error.log"),
      merge_logs: true,
    },
    {
      name: "decoded-connect",
      cwd: HOME,
      script: VENV_PY,
      // Full throughput: 500 candidates/run, $10/day budget, runs every 30 min.
      // cron_restart fires after extract has had time to queue new papers.
      args: "-m decoded.connect.worker --limit 500 --daily-budget 10 --total-budget 10",
      interpreter: "none",
      env: {
        PYTHONPATH: HOME,
        DATABASE_URL,
        NEO4J_URI,
        NEO4J_USER: "neo4j",
        NEO4J_PASSWORD: _env.NEO4J_PASSWORD || "",
        REDIS_URL,
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || "",
      },
      autorestart: false,
      cron_restart: "15 * * * *", // every hour at :15 (after extract has run)
      max_restarts: 0,
      min_uptime: "10s",
      watch: false,
      max_memory_restart: "2G",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: path.join(LOGS, "connect-out.log"),
      error_file: path.join(LOGS, "connect-error.log"),
      merge_logs: true,
    },
    {
      name: "decoded-critique",
      cwd: HOME,
      script: VENV_PY,
      // Full throughput: 200 briefs/run, $5/day budget, runs every 4 hours.
      args: "-m decoded.critique.worker --limit 200 --daily-budget 5 --total-budget 5",
      interpreter: "none",
      env: {
        PYTHONPATH: HOME,
        DATABASE_URL,
        NEO4J_URI,
        NEO4J_USER: "neo4j",
        NEO4J_PASSWORD: _env.NEO4J_PASSWORD || "",
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || "",
        REDIS_URL,
      },
      autorestart: false,
      cron_restart: "30 */4 * * *", // every 4 hours at :30
      max_restarts: 0,
      min_uptime: "10s",
      watch: false,
      max_memory_restart: "1G",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: path.join(LOGS, "critique-out.log"),
      error_file: path.join(LOGS, "critique-error.log"),
      merge_logs: true,
    },
    {
      name: "decoded-outreach",
      cwd: HOME,
      script: VENV_PY,
      args: "-m decoded.outreach.processor --limit 10",
      interpreter: "none",
      env: {
        // AutoAIBiz still lives at /Users/whit on Mini. When this gets migrated
        // to Studio (Phase 9), AutoAIBiz may follow or may stay on Mini as
        // worker — adjust this PYTHONPATH then.
        PYTHONPATH: `${HOME}:/Users/whit/Projects/AutoAIBiz`,
        DATABASE_URL,
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || "",
        NCBI_API_KEY: _env.NCBI_API_KEY || "",
      },
      // Runs on a schedule — processes up to 10 pending items then exits.
      // PM2 restarts it every hour. autorestart: false prevents runaway retries.
      autorestart: false,
      cron_restart: "0 * * * *", // Every hour
      max_restarts: 0,
      watch: false,
      max_memory_restart: "512M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: path.join(LOGS, "outreach-out.log"),
      error_file: path.join(LOGS, "outreach-error.log"),
      merge_logs: true,
    },
    {
      name: "decoded-pearl-bridge",
      cwd: HOME,
      script: VENV_PY,
      args: "-m decoded.pearl.batch_bridge --unbridged --limit 100",
      interpreter: "none",
      env: {
        PYTHONPATH: HOME,
        DATABASE_URL,
      },
      // Runs at 3 AM daily (after Decoded extract/connect finish).
      // 3 AM not 2 AM: extract+connect may not finish before 2 AM as corpus grows.
      cron_restart: "0 3 * * *",
      autorestart: false,
      max_restarts: 0,
      watch: false,
      max_memory_restart: "1G",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: path.join(LOGS, "pearl-bridge-out.log"),
      error_file: path.join(LOGS, "pearl-bridge-error.log"),
      merge_logs: true,
    },
    {
      name: "decoded-explorer",
      cwd: path.join(HOME, "explorer"),
      script: "node_modules/.bin/vite",
      args: "preview --port 5173 --host 0.0.0.0",
      interpreter: "node",
      autorestart: true,
      max_restarts: 5,
      restart_delay: 10000,
      watch: false,
      max_memory_restart: "512M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: path.join(LOGS, "explorer-out.log"),
      error_file: path.join(LOGS, "explorer-error.log"),
      merge_logs: true,
    },
  ],
};
