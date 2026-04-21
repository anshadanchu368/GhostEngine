import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { createReadStream } from 'fs';
import { basename } from 'path';
import logger from '../logger.js';

const AWS_REGION = process.env.AWS_REGION ?? 'us-east-1';
const BUCKET_NAME = process.env.S3_BUCKET_NAME;

if (!BUCKET_NAME) {
  throw new Error('S3_BUCKET_NAME environment variable is not set');
}

const s3Client = new S3Client({ region: AWS_REGION });

export class S3Uploader {
  async upload(localPath, jobId) {
    const key = `jobs/${jobId}/${basename(localPath)}`;
    const fileStream = createReadStream(localPath);

    const command = new PutObjectCommand({
      Bucket: BUCKET_NAME,
      Key: key,
      Body: fileStream,
      ContentType: 'model/gltf-binary',
    });

    logger.info({ job_id: jobId, key }, 'Uploading to S3');
    await s3Client.send(command);

    const url = `https://${BUCKET_NAME}.s3.${AWS_REGION}.amazonaws.com/${key}`;
    logger.info({ job_id: jobId, url }, 'S3 upload complete');
    return url;
  }
}

export default new S3Uploader();
