import dotenv from 'dotenv';
dotenv.config();

import express from 'express';
import cors from 'cors';
import authRoutes from './routes/authRoutes.js';
import worksheetRoutes from './routes/worksheetRoutes.js';
import { closeBrowser } from './services/pdfGenerator.js';
import { initDatabase } from './services/db.js';

const app = express();
const port = Number(process.env.PORT || 3001);

app.use(cors());
app.use(express.json({ limit: '15mb' }));

// ─── Health Check ──────────────────────────────────────────

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, service: 'worksheet-backend' });
});

// ─── Routes ────────────────────────────────────────────────

app.use('/api/auth', authRoutes);
app.use('/api/worksheets', worksheetRoutes);

// ─── Start Server (after DB init) ──────────────────────────

(async () => {
  try {
    await initDatabase();
    app.listen(port, () => {
      console.log(`Worksheet backend listening on http://localhost:${port}`);
    });
  } catch (err) {
    console.error('Failed to start server:', err.message);
    process.exit(1);
  }
})();

// ─── Graceful Shutdown ─────────────────────────────────────

const shutdown = async () => {
  console.log('\nShutting down...');
  await closeBrowser();
  process.exit(0);
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);