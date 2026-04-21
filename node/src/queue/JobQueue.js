import { EventEmitter } from 'events';
import logger from '../logger.js';

export class JobQueue extends EventEmitter {
  #queue = [];
  #running = false;

  enqueue(job) {
    // job: { id: string, fn: async function returning result }
    return new Promise((resolve, reject) => {
      this.#queue.push({ job, resolve, reject });
      this.#drain();
    });
  }

  get size() {
    return this.#queue.length;
  }

  async #drain() {
    if (this.#running || this.#queue.length === 0) return;
    this.#running = true;
    const { job, resolve, reject } = this.#queue.shift();
    logger.info({ job_id: job.id, queue_size: this.#queue.length }, 'Job dequeued');
    try {
      const result = await job.fn();
      resolve(result);
    } catch (err) {
      reject(err);
    } finally {
      this.#running = false;
      this.#drain();
    }
  }
}

export default new JobQueue();
