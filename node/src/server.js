import http from 'http';
import express from 'express';
import multer from 'multer';
import { v4 as uuidv4 } from 'uuid';
import logger from './logger.js';
import jobQueue from './queue/JobQueue.js';
import orchestrator from './ml/MLOrchestrator.js';
import s3Uploader from './storage/S3Uploader.js';
import broadcaster from './ws/JobBroadcaster.js';
import { createWebSocketServer } from './ws/WebSocketServer.js';

const PORT = Number(process.env.NODE_PORT ?? 3000);
const SHARED_TMP_DIR = process.env.SHARED_TMP_DIR ?? '/dev/shm/ghostfabric';

const app = express();

const upload = multer({
  dest: SHARED_TMP_DIR,
  limits: { fileSize: 50 * 1024 * 1024 },
  fileFilter(_req, file, cb) {
    const allowed = ['image/jpeg', 'image/png'];
    if (!allowed.includes(file.mimetype)) {
      return cb(new Error('Unsupported media type. Use image/jpeg or image/png.'));
    }
    cb(null, true);
  },
});

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', queue_size: jobQueue.size });
});

app.post('/jobs', upload.single('image'), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'No image file provided' });
  }

  const jobId = uuidv4();
  const imagePath = req.file.path;

  logger.info({ job_id: jobId, image_path: imagePath }, 'Job submitted');
  broadcaster.broadcast(jobId, 'queued', 0);

  res.status(202).json({ job_id: jobId, status: 'queued' });

  jobQueue
    .enqueue({
      id: jobId,
      fn: async () => {
        try {
          broadcaster.broadcast(jobId, 'processing:segmentation', 10);
          const result = await orchestrator.process(imagePath);

          if (result.status === 'completed') {
            broadcaster.broadcast(jobId, 'uploading', 85);
            const glbUrl = await s3Uploader.upload(result.glb_path, jobId);
            broadcaster.broadcast(jobId, 'completed', 100, glbUrl);
            logger.info({ job_id: jobId, glb_url: glbUrl }, 'Job completed');
          } else {
            broadcaster.broadcast(jobId, result.status, 0);
            logger.warn({ job_id: jobId, status: result.status }, 'Job failed in pipeline');
          }
        } catch (err) {
          broadcaster.broadcast(jobId, 'failed:internal', 0);
          logger.error({ job_id: jobId, err: err.message }, 'Job failed with exception');
        }
      },
    })
    .catch((err) => {
      broadcaster.broadcast(jobId, 'failed:internal', 0);
      logger.error({ job_id: jobId, err: err.message }, 'Queue processing error');
    });
});

app.use((err, _req, res, _next) => {
  logger.warn({ err: err.message }, 'Request error');
  const status = err.message.includes('Unsupported media type') ? 415 : 500;
  res.status(status).json({ error: err.message });
});

const httpServer = http.createServer(app);
createWebSocketServer(httpServer);

httpServer.listen(PORT, () => {
  logger.info({ port: PORT }, 'GhostFabric Node server listening');
});

export default httpServer;
