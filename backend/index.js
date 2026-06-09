import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';

dotenv.config();

const app = express();
const port = Number(process.env.PORT || 3001);
const awsRegion = process.env.AWS_REGION;
const bucketName = process.env.AWS_S3_BUCKET;
const keyPrefix = normalizePrefix(process.env.AWS_S3_KEY_PREFIX || '');

if (!awsRegion || !bucketName) {
  console.warn('Missing AWS_REGION or AWS_S3_BUCKET. S3 upload requests will fail until they are set.');
}

const s3Client = new S3Client({
  region: awsRegion || 'us-east-1',
});

app.use(cors());
app.use(express.json({ limit: '15mb' }));

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, service: 'worksheet-backend' });
});

app.post('/api/worksheets/s3', async (req, res) => {
  try {
    if (!bucketName) {
      return res.status(500).json({ message: 'AWS_S3_BUCKET is not configured.' });
    }

    const html = typeof req.body?.html === 'string' ? req.body.html.trim() : '';
    if (!html) {
      return res.status(400).json({ message: 'Worksheet HTML is required.' });
    }

    const fileName = buildFileName(req.body?.fileName);
    const folderPath = buildFolderPath(req.body?.folderPath);
    const objectKey = joinKeyParts(keyPrefix, folderPath, fileName);

    const result = await s3Client.send(new PutObjectCommand({
      Bucket: bucketName,
      Key: objectKey,
      Body: html,
      ContentType: 'text/html; charset=utf-8',
      CacheControl: 'no-cache',
    }));

    res.json({
      message: 'Worksheet saved to S3.',
      bucket: bucketName,
      key: objectKey,
      eTag: result.ETag || null,
      location: `s3://${bucketName}/${objectKey}`,
    });
  } catch (error) {
    console.error('S3 upload failed:', error);
    res.status(500).json({
      message: 'Failed to save worksheet to S3.',
      error: error?.message || 'Unknown error',
    });
  }
});

app.listen(port, () => {
  console.log(`Worksheet backend listening on http://localhost:${port}`);
});

function buildFileName(value) {
  const raw = typeof value === 'string' ? value.trim() : '';
  const base = raw || 'worksheet';
  const cleaned = base
    .replace(/\.[^.\/\\]+$/, '')
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[-_.]+|[-_.]+$/g, '')
    .toLowerCase();

  return `${cleaned || 'worksheet'}.html`;
}

function buildFolderPath(value) {
  if (typeof value !== 'string') return '';

  return value
    .split(/[\\/]+/)
    .map((segment) => segment.trim())
    .filter(Boolean)
    .map((segment) => segment.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/-+/g, '-').replace(/^[-_.]+|[-_.]+$/g, '').toLowerCase())
    .filter(Boolean)
    .join('/');
}

function normalizePrefix(value) {
  return typeof value === 'string'
    ? value.split(/[\\/]+/).filter(Boolean).join('/')
    : '';
}

function joinKeyParts(...parts) {
  return parts.filter(Boolean).join('/').replace(/\/+/g, '/');
}