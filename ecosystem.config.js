/**
 * Decoded PM2 Ecosystem Config
 *
 * Processes:
 *   decoded-api   — FastAPI + uvicorn (REST API + Pearl connectome)
 *   decoded-explorer — Vite React frontend (served by nginx in prod)
 *
 * Start:  pm2 start ecosystem.config.js
 * Stop:   pm2 stop decoded-api
 * Logs:   pm2 logs decoded-api
 * Save:   pm2 save
 */

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
        DECODED_API_URL: 'https://connectome.theencodedhumanproject.com',
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
