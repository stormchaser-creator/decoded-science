/**
 * Decoded PM2 Ecosystem Config
 *
 * Processes:
 *   decoded-api      — FastAPI + uvicorn (REST API + Pearl connectome)
 *   decoded-extract  — Paper extraction worker (Claude Haiku)
 *   decoded-graph    — Neo4j graph sync worker (batch, runs on interval)
 *   decoded-connect  — Connection discovery worker (graph + LLM)
 *   decoded-critique — Paper critique worker (Claude Sonnet)
 *   decoded-explorer — Vite React frontend (served by nginx in prod)
 *
 * Start:  pm2 start ecosystem.config.js
 * Stop:   pm2 stop decoded-api
 * Logs:   pm2 logs decoded-api
 * Save:   pm2 save
 */

// Read secrets from .env at config load time (file is gitignored)
const fs = require('fs');
const path = require('path');
const _env = {};
try {
  fs.readFileSync(path.join(__dirname, '.env'), 'utf8').split('\n').forEach(line => {
    const m = line.match(/^([^#=\s][^=]*)=(.*)$/);
    if (m) _env[m[1].trim()] = m[2].trim();
  });
} catch (_) {}

module.exports = {
  apps: [
    {
      name: 'decoded-api',
      cwd: '/Users/whit/Projects/Decoded',
      script: '/Users/whit/Projects/Decoded/.venv/bin/uvicorn',
      args: 'decoded.api.main:app --host 0.0.0.0 --port 8000 --workers 2',
      interpreter: 'none',
      env: {
        PYTHONPATH: '/Users/whit/Projects/Decoded',
        DATABASE_URL: 'postgresql://whit@localhost:5432/encoded_human',
        NEO4J_URI: 'bolt://localhost:7687',
        NEO4J_USER: 'neo4j',
        REDIS_URL: 'redis://localhost:6379/0',
        DECODED_API_URL: 'https://connectome.theencodedhuman.com',
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      min_uptime: '10s',
      watch: false,
      max_memory_restart: '512M',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      out_file: '/Users/whit/Projects/Decoded/logs/api-out.log',
      error_file: '/Users/whit/Projects/Decoded/logs/api-error.log',
      merge_logs: true,
    },
    {
      name: 'decoded-extract',
      cwd: '/Users/whit/Projects/Decoded',
      script: '/Users/whit/Projects/Decoded/.venv/bin/python',
      args: '-m decoded.extract.worker --limit 500 --concurrency 5',
      interpreter: 'none',
      env: {
        PYTHONPATH: '/Users/whit/Projects/Decoded',
        DATABASE_URL: 'postgresql://whit@localhost:5432/encoded_human',
        NEO4J_URI: 'bolt://localhost:7687',
        NEO4J_USER: 'neo4j',
        REDIS_URL: 'redis://localhost:6379/0',
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || '',
      },
      autorestart: true,
      max_restarts: 50,
      restart_delay: 30000,
      min_uptime: '5s',
      watch: false,
      max_memory_restart: '512M',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      out_file: '/Users/whit/Projects/Decoded/logs/extract-out.log',
      error_file: '/Users/whit/Projects/Decoded/logs/extract-error.log',
      merge_logs: true,
    },
    {
      name: 'decoded-graph',
      cwd: '/Users/whit/Projects/Decoded',
      script: '/Users/whit/Projects/Decoded/.venv/bin/python',
      args: '-m decoded.graph.worker --limit 5000',
      interpreter: 'none',
      env: {
        PYTHONPATH: '/Users/whit/Projects/Decoded',
        DATABASE_URL: 'postgresql://whit@localhost:5432/encoded_human',
        NEO4J_URI: 'bolt://localhost:7687',
        NEO4J_USER: 'neo4j',
      },
      autorestart: true,
      max_restarts: 50,
      restart_delay: 300000,
      min_uptime: '10s',
      watch: false,
      max_memory_restart: '512M',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      out_file: '/Users/whit/Projects/Decoded/logs/graph-out.log',
      error_file: '/Users/whit/Projects/Decoded/logs/graph-error.log',
      merge_logs: true,
    },
    {
      name: 'decoded-connect',
      cwd: '/Users/whit/Projects/Decoded',
      script: '/Users/whit/Projects/Decoded/.venv/bin/python',
      args: '-m decoded.connect.worker --limit 500',
      interpreter: 'none',
      env: {
        PYTHONPATH: '/Users/whit/Projects/Decoded',
        DATABASE_URL: 'postgresql://whit@localhost:5432/encoded_human',
        NEO4J_URI: 'bolt://localhost:7687',
        NEO4J_USER: 'neo4j',
        REDIS_URL: 'redis://localhost:6379/0',
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || '',
      },
      autorestart: true,
      max_restarts: 20,
      restart_delay: 60000,
      min_uptime: '10s',
      watch: false,
      max_memory_restart: '512M',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      out_file: '/Users/whit/Projects/Decoded/logs/connect-out.log',
      error_file: '/Users/whit/Projects/Decoded/logs/connect-error.log',
      merge_logs: true,
    },
    {
      name: 'decoded-critique',
      cwd: '/Users/whit/Projects/Decoded',
      script: '/Users/whit/Projects/Decoded/.venv/bin/python',
      args: '-m decoded.critique.worker --limit 100',
      interpreter: 'none',
      env: {
        PYTHONPATH: '/Users/whit/Projects/Decoded',
        DATABASE_URL: 'postgresql://whit@localhost:5432/encoded_human',
        NEO4J_URI: 'bolt://localhost:7687',
        NEO4J_USER: 'neo4j',
        ANTHROPIC_API_KEY: _env.ANTHROPIC_API_KEY || '',
      },
      autorestart: true,
      max_restarts: 30,
      restart_delay: 120000,
      min_uptime: '10s',
      watch: false,
      max_memory_restart: '512M',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      out_file: '/Users/whit/Projects/Decoded/logs/critique-out.log',
      error_file: '/Users/whit/Projects/Decoded/logs/critique-error.log',
      merge_logs: true,
    },
    {
      name: 'decoded-explorer',
      cwd: '/Users/whit/Projects/Decoded/explorer',
      script: 'node_modules/.bin/vite',
      args: 'preview --port 5173 --host 0.0.0.0',
      interpreter: 'node',
      autorestart: true,
      max_restarts: 5,
      restart_delay: 10000,
      watch: false,
      max_memory_restart: '256M',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      out_file: '/Users/whit/Projects/Decoded/logs/explorer-out.log',
      error_file: '/Users/whit/Projects/Decoded/logs/explorer-error.log',
      merge_logs: true,
    },
  ],
};
