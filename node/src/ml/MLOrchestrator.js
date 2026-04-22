import CircuitBreaker from 'opossum';
import FormData from 'form-data';
import fetch from 'node-fetch';
import { createReadStream } from 'fs';
import logger from '../logger.js';

const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL ?? 'http://localhost:8000';

const CIRCUIT_BREAKER_OPTIONS = {
  timeout: Number(process.env.CIRCUIT_BREAKER_TIMEOUT ?? 120000),
  errorThresholdPercentage: Number(process.env.CIRCUIT_BREAKER_ERROR_THRESHOLD ?? 50),
  resetTimeout: Number(process.env.CIRCUIT_BREAKER_RESET_TIMEOUT ?? 30000),
};

async function callPythonProcess(imagePath) {
  const form = new FormData();
  form.append('image', createReadStream(imagePath), {
    contentType: 'image/jpeg',
  });

  const response = await fetch(`${PYTHON_SERVICE_URL}/process`, {
    method: 'POST',
    body: form,
    headers: form.getHeaders(),
  });

  if (!response.ok) {
    const text = await response.text();
    const truncated = text.slice(0, 200);
    throw new Error(`Python service error ${response.status}: ${truncated}`);
  }

  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('model/gltf-binary')) {
    const buffer = await response.buffer();
    return { status: 'completed', glb_buffer: buffer };
  }

  const result = await response.json();
  if (typeof result.status === 'string' && result.status.startsWith('failed:')) {
    throw new Error(`Pipeline failure [${result.status}]: ${result.error ?? 'unknown'}`);
  }

  return result;
}

const breaker = new CircuitBreaker(callPythonProcess, CIRCUIT_BREAKER_OPTIONS);

breaker.on('open', () => logger.warn('Circuit breaker opened'));
breaker.on('halfOpen', () => logger.info('Circuit breaker half-open'));
breaker.on('close', () => logger.info('Circuit breaker closed'));
breaker.on('fallback', (result) => logger.warn({ result }, 'Circuit breaker fallback'));

export class MLOrchestrator {
  async process(imagePath) {
    return breaker.fire(imagePath);
  }

  get circuitBreakerState() {
    return breaker.status;
  }
}

export default new MLOrchestrator();
