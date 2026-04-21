import { EventEmitter } from 'events';
import logger from '../logger.js';

export class JobBroadcaster extends EventEmitter {
  #clients = new Set();

  addClient(ws) {
    this.#clients.add(ws);
    ws.once('close', () => this.#clients.delete(ws));
  }

  broadcast(jobId, status, progress, glbUrl = null) {
    const payload = JSON.stringify({
      event: 'job_status',
      job_id: jobId,
      status,
      progress,
      ...(glbUrl ? { glb_url: glbUrl } : {}),
    });

    for (const client of this.#clients) {
      if (client.readyState === 1) {
        client.send(payload);
      }
    }

    logger.info(
      { job_id: jobId, status, progress, client_count: this.#clients.size },
      'Broadcast sent',
    );
  }

  get clientCount() {
    return this.#clients.size;
  }
}

export default new JobBroadcaster();
