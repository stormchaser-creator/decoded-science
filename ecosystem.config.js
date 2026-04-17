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
 */

// Read secrets from .env at config load time (file is gitignored)
const fs = require("fs");
const path = require("path");
const _env = {};
try {
  fs.readFileSync(path.join(__dirname, ".env"), "utf8")
    .split("\n")
    .forEach((line) => {
      const m = line.match(/^([^#=\s][^=]*)=(.*)$/);
      if (m) _env[m[1].trim()] = m[2].trim();
    });
} catch (_) {}

module.exports = {
  apps: [
    {
      name: "decoded-api",
      cwd: "/Users/whit/Projects/Decoded",
      script: "/Users/whit/Projects/Decoded/.venv/bin/uvicorn",
      args: "decoded.api.main:app --host 0.0.0.0 --port 8000 --workers 2",
      interpreter: "none",
      env: {
        PYTHONPATH: "/Users/whit/Projects/Decoded",
        DATABASE_URL: "postgresql://whit@localhost:5432/encoded_human",
        NEO4J_URI: "bolt://localhost:7687",
        NEO4J_USER: "neo4j",
        NEO4J_PASSWORD: _env.NEO4J_PASSWORD || "",
        REDIS_URL: "redis://localhost:6379/0",
        DECODED_JWT_SECRET: _env.DECODED_JWT_SECRET || "",
        DECODED_API_URL: "https://connectome.theencodedhuman.com",
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      min_uptime: "10s",
      watch: false,
      max_memory_restart: "512M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: "/Users/whit/Projects/Decoded/logs/api-out.log",
      error_file: "/Users/whit/Projects/Decoded/logs/api-error.log",
      merge_logs: true,
    },
    {
      name: "decoded-extract",
      cwd: "/Users/whit/Projects/Decoded",
      script: "/Users/whit/Projects/Decoded/.venv/bin/python",
      // Paced throughput: 3 concurrent, 50/batch, $50/day budget.
      // 50 papers × ~$0.011 = ~$0.55/batch. At 15-min restart_delay:
      //   ~3 batches/hr × $0.55 = ~$1.65/hr → $50 spread over ~30 hours.
      // This keeps extraction flowing all day instead of exhausting budget by 9:30 AM.
      // connect/critique budgets are now tracked independently (per-task) so they
      // are never blocked by extract's spend.
      args: "-m decoded.extract.worker --limit 50 --concurrency 3 --daily-budget 50 --total-budget 50",
      interpreter: "none",
      env: {
        PYTHONPATH: "/Users/whit/Projects/Decoded",
        DATABASE_URL: "postgresql://whit@localhost:5432/encoded_human",
        NEO4J_URI: "bolt://localhost:7687",
        NEO4J_USER: "neo4j",
        NEO4J_PASSWORD: _env.NEO4J_PASSWORD || "",
        REDIS_URL: "redis://localhost:6379/0",
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || "",
        DECODE_EMPTY_BACKOFF: "3600", // sleep 1 hour when budget/queue empty
        DECODE_ERROR_BACKOFF: "120",
      },
      autorestart: true, // continuously process — budget check prevents tight loops
      max_restarts: 500,
      restart_delay: 900000, // 15 min between batches — paces $50/day over ~30 hours
      min_uptime: "10s",
      watch: false,
      max_memory_restart: "512M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: "/Users/whit/Projects/Decoded/logs/extract-out.log",
      error_file: "/Users/whit/Projects/Decoded/logs/extract-error.log",
      merge_logs: true,
    },
    {
      name: "decoded-graph",
      cwd: "/Users/whit/Projects/Decoded",
      script: "/Users/whit/Projects/Decoded/.venv/bin/python",
      args: "-m decoded.graph.worker --limit 500",
      interpreter: "none",
      env: {
        PYTHONPATH: "/Users/whit/Projects/Decoded",
        DATABASE_URL: "postgresql://whit@localhost:5432/encoded_human",
        NEO4J_URI: "bolt://localhost:7687",
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
      max_memory_restart: "512M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: "/Users/whit/Projects/Decoded/logs/graph-out.log",
      error_file: "/Users/whit/Projects/Decoded/logs/graph-error.log",
      merge_logs: true,
    },
    {
      name: "decoded-connect",
      cwd: "/Users/whit/Projects/Decoded",
      script: "/Users/whit/Projects/Decoded/.venv/bin/python",
      // Full throughput: 500 candidates/run, $10/day budget, runs every 30 min.
      // cron_restart fires after extract has had time to queue new papers.
      args: "-m decoded.connect.worker --limit 500 --daily-budget 10 --total-budget 10",
      interpreter: "none",
      env: {
        PYTHONPATH: "/Users/whit/Projects/Decoded",
        DATABASE_URL: "postgresql://whit@localhost:5432/encoded_human",
        NEO4J_URI: "bolt://localhost:7687",
        NEO4J_USER: "neo4j",
        NEO4J_PASSWORD: _env.NEO4J_PASSWORD || "",
        REDIS_URL: "redis://localhost:6379/0",
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || "",
      },
      autorestart: false,
      cron_restart: "15 * * * *", // every hour at :15 (after extract has run)
      max_restarts: 0,
      min_uptime: "10s",
      watch: false,
      max_memory_restart: "512M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: "/Users/whit/Projects/Decoded/logs/connect-out.log",
      error_file: "/Users/whit/Projects/Decoded/logs/connect-error.log",
      merge_logs: true,
    },
    {
      name: "decoded-critique",
      cwd: "/Users/whit/Projects/Decoded",
      script: "/Users/whit/Projects/Decoded/.venv/bin/python",
      // Full throughput: 200 briefs/run, $5/day budget, runs every 4 hours.
      args: "-m decoded.critique.worker --limit 200 --daily-budget 5 --total-budget 5",
      interpreter: "none",
      env: {
        PYTHONPATH: "/Users/whit/Projects/Decoded",
        DATABASE_URL: "postgresql://whit@localhost:5432/encoded_human",
        NEO4J_URI: "bolt://localhost:7687",
        NEO4J_USER: "neo4j",
        NEO4J_PASSWORD: _env.NEO4J_PASSWORD || "",
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || "",
        REDIS_URL: "redis://localhost:6379/0",
      },
      autorestart: false,
      cron_restart: "30 */4 * * *", // every 4 hours at :30
      max_restarts: 0,
      min_uptime: "10s",
      watch: false,
      max_memory_restart: "512M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: "/Users/whit/Projects/Decoded/logs/critique-out.log",
      error_file: "/Users/whit/Projects/Decoded/logs/critique-error.log",
      merge_logs: true,
    },
    {
      name: "decoded-outreach",
      cwd: "/Users/whit/Projects/Decoded",
      script: "/Users/whit/Projects/Decoded/.venv/bin/python",
      args: "-m decoded.outreach.processor --limit 10",
      interpreter: "none",
      env: {
        PYTHONPATH:
          "/Users/whit/Projects/Decoded:/Users/whit/Projects/AutoAIBiz",
        DATABASE_URL: "postgresql://whit@localhost:5432/encoded_human",
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || "",
        NCBI_API_KEY: _env.NCBI_API_KEY || "",
      },
      // Runs on a schedule — processes up to 10 pending items then exits.
      // PM2 restarts it every hour. autorestart: false prevents runaway retries.
      autorestart: false,
      cron_restart: "0 * * * *", // Every hour
      max_restarts: 0,
      watch: false,
      max_memory_restart: "256M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: "/Users/whit/Projects/Decoded/logs/outreach-out.log",
      error_file: "/Users/whit/Projects/Decoded/logs/outreach-error.log",
      merge_logs: true,
    },
    {
      name: "decoded-pearl-bridge",
      cwd: "/Users/whit/Projects/Decoded",
      script: "/Users/whit/Projects/Decoded/.venv/bin/python",
      args: "-m decoded.pearl.batch_bridge --unbridged --limit 100",
      interpreter: "none",
      env: {
        PYTHONPATH: "/Users/whit/Projects/Decoded",
        DATABASE_URL: "postgresql://whit@localhost:5432/encoded_human",
      },
      // Runs at 3 AM daily (after Decoded extract/connect finish).
      // 3 AM not 2 AM: extract+connect may not finish before 2 AM as corpus grows.
      cron_restart: "0 3 * * *",
      autorestart: false,
      max_restarts: 0,
      watch: false,
      max_memory_restart: "512M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: "/Users/whit/Projects/Decoded/logs/pearl-bridge-out.log",
      error_file: "/Users/whit/Projects/Decoded/logs/pearl-bridge-error.log",
      merge_logs: true,
    },
    {
      name: "decoded-explorer",
      cwd: "/Users/whit/Projects/Decoded/explorer",
      script: "node_modules/.bin/vite",
      args: "preview --port 5173 --host 0.0.0.0",
      interpreter: "node",
      autorestart: true,
      max_restarts: 5,
      restart_delay: 10000,
      watch: false,
      max_memory_restart: "256M",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      out_file: "/Users/whit/Projects/Decoded/logs/explorer-out.log",
      error_file: "/Users/whit/Projects/Decoded/logs/explorer-error.log",
      merge_logs: true,
    },
  ],
};
