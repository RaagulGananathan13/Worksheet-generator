import { Router } from 'express';
import { S3Client, PutObjectCommand, DeleteObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { randomUUID } from 'crypto';
import { requireAuth } from '../middleware/authMiddleware.js';
import { generatePDFFromHTML } from '../services/pdfGenerator.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const WORKSHEETS_FILE = join(__dirname, '..', 'data', 'worksheets.json');

const router = Router();

// ─── S3 Setup (lazy — env may not be loaded at import time) ──

let _s3Client = null;
function getS3Client() {
  if (!_s3Client) {
    _s3Client = new S3Client({ region: process.env.AWS_REGION || 'us-east-1' });
  }
  return _s3Client;
}

function getBucketName() {
  return process.env.AWS_S3_BUCKET;
}

function getKeyPrefix() {
  return normalizePrefix(process.env.AWS_S3_KEY_PREFIX || '');
}

// ─── Helpers ───────────────────────────────────────────────

function loadWorksheets() {
  try {
    const data = readFileSync(WORKSHEETS_FILE, 'utf-8');
    return JSON.parse(data);
  } catch {
    return [];
  }
}

function saveWorksheets(worksheets) {
  const dir = dirname(WORKSHEETS_FILE);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  writeFileSync(WORKSHEETS_FILE, JSON.stringify(worksheets, null, 2), 'utf-8');
}

function buildFileName(value) {
  const raw = typeof value === 'string' ? value.trim() : '';
  const base = raw || 'worksheet';
  const cleaned = base
    .replace(/\.[^.\/\\]+$/, '')
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[-_.]+|[-_.]+$/g, '')
    .toLowerCase();
  return cleaned || 'worksheet';
}

function buildActivityFolder(value) {
  if (typeof value !== 'string' || !value.trim()) return 'general';
  return value
    .trim()
    .replace(/[^a-zA-Z0-9._\s-]+/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[-_.]+|[-_.]+$/g, '')
    .toLowerCase() || 'general';
}

function normalizePrefix(value) {
  return typeof value === 'string'
    ? value.split(/[\\/]+/).filter(Boolean).join('/')
    : '';
}

function joinKeyParts(...parts) {
  return parts.filter(Boolean).join('/').replace(/\/+/g, '/');
}

// ─── POST /api/worksheets/s3 — Save HTML + PDF pair ────────

router.post('/s3', requireAuth, async (req, res) => {
  try {
    const bucketName = getBucketName();
    const keyPrefix = getKeyPrefix();
    const s3Client = getS3Client();

    if (!bucketName) {
      return res.status(500).json({ message: 'AWS_S3_BUCKET is not configured.' });
    }

    const html = typeof req.body?.html === 'string' ? req.body.html.trim() : '';
    if (!html) {
      return res.status(400).json({ message: 'Worksheet HTML is required.' });
    }

    const rawFileName = buildFileName(req.body?.fileName);
    const activityName = req.body?.activityName || req.body?.folderPath || 'general';
    const activityFolder = buildActivityFolder(activityName);

    // Build S3 keys for both HTML and PDF
    const htmlKey = joinKeyParts(keyPrefix, activityFolder, `${rawFileName}.html`);
    const pdfKey = joinKeyParts(keyPrefix, activityFolder, `${rawFileName}.pdf`);

    // 1. Upload HTML
    await s3Client.send(new PutObjectCommand({
      Bucket: bucketName,
      Key: htmlKey,
      Body: html,
      ContentType: 'text/html; charset=utf-8',
      CacheControl: 'no-cache',
    }));

    // 2. Generate PDF from HTML and upload
    let pdfUploaded = false;
    try {
      const pdfBuffer = await generatePDFFromHTML(html);
      await s3Client.send(new PutObjectCommand({
        Bucket: bucketName,
        Key: pdfKey,
        Body: pdfBuffer,
        ContentType: 'application/pdf',
        CacheControl: 'no-cache',
      }));
      pdfUploaded = true;
    } catch (pdfError) {
      console.error('PDF generation/upload failed (HTML was still saved):', pdfError.message);
    }

    // 3. Save worksheet metadata
    const worksheets = loadWorksheets();
    const worksheetId = randomUUID();

    const worksheetRecord = {
      id: worksheetId,
      fileName: rawFileName,
      activityName: activityName.trim(),
      activityFolder,
      s3HtmlKey: htmlKey,
      s3PdfKey: pdfUploaded ? pdfKey : null,
      ownerId: req.user.id,
      ownerEmail: req.user.email,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    worksheets.push(worksheetRecord);
    saveWorksheets(worksheets);

    res.json({
      message: pdfUploaded
        ? 'Worksheet saved to S3 (HTML + PDF).'
        : 'Worksheet HTML saved to S3. PDF generation failed.',
      worksheet: worksheetRecord,
      bucket: bucketName,
      htmlLocation: `s3://${bucketName}/${htmlKey}`,
      pdfLocation: pdfUploaded ? `s3://${bucketName}/${pdfKey}` : null,
    });
  } catch (error) {
    console.error('S3 upload failed:', error);
    res.status(500).json({
      message: 'Failed to save worksheet to S3.',
      error: error?.message || 'Unknown error',
    });
  }
});

// ─── GET /api/worksheets — List all worksheets ─────────────

router.get('/', requireAuth, (req, res) => {
  try {
    const worksheets = loadWorksheets();
    // Return all worksheets with ownership flag
    const result = worksheets.map((w) => ({
      ...w,
      isOwner: w.ownerId === req.user.id,
    }));

    // Sort by most recent first
    result.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

    res.json({ worksheets: result });
  } catch (error) {
    console.error('Failed to list worksheets:', error);
    res.status(500).json({ message: 'Failed to load worksheets.' });
  }
});

// ─── GET /api/worksheets/:id — Get single worksheet ────────

router.get('/:id', requireAuth, (req, res) => {
  try {
    const worksheets = loadWorksheets();
    const worksheet = worksheets.find((w) => w.id === req.params.id);

    if (!worksheet) {
      return res.status(404).json({ message: 'Worksheet not found.' });
    }

    res.json({
      worksheet: {
        ...worksheet,
        isOwner: worksheet.ownerId === req.user.id,
      },
    });
  } catch (error) {
    console.error('Failed to get worksheet:', error);
    res.status(500).json({ message: 'Failed to load worksheet.' });
  }
});

// ─── GET /api/worksheets/:id/content — Fetch HTML from S3 ──

router.get('/:id/content', requireAuth, async (req, res) => {
  try {
    const worksheets = loadWorksheets();
    const worksheet = worksheets.find((w) => w.id === req.params.id);

    if (!worksheet) {
      return res.status(404).json({ message: 'Worksheet not found.' });
    }

    const bucketName = getBucketName();
    const s3Client = getS3Client();

    if (!bucketName) {
      return res.status(500).json({ message: 'AWS_S3_BUCKET is not configured.' });
    }

    const response = await s3Client.send(new GetObjectCommand({
      Bucket: bucketName,
      Key: worksheet.s3HtmlKey,
    }));

    // Stream the S3 body to a string
    const chunks = [];
    for await (const chunk of response.Body) {
      chunks.push(chunk);
    }
    const html = Buffer.concat(chunks).toString('utf-8');

    res.json({
      worksheet: {
        ...worksheet,
        isOwner: worksheet.ownerId === req.user.id,
      },
      html,
    });
  } catch (error) {
    console.error('Failed to fetch worksheet content:', error);
    res.status(500).json({ message: 'Failed to load worksheet content from S3.' });
  }
});

// ─── PUT /api/worksheets/:id — Update worksheet (owner only)

router.put('/:id', requireAuth, async (req, res) => {
  try {
    const worksheets = loadWorksheets();
    const index = worksheets.findIndex((w) => w.id === req.params.id);

    if (index === -1) {
      return res.status(404).json({ message: 'Worksheet not found.' });
    }

    if (worksheets[index].ownerId !== req.user.id) {
      return res.status(403).json({ message: 'You can only update your own worksheets.' });
    }

    const html = typeof req.body?.html === 'string' ? req.body.html.trim() : '';
    if (!html) {
      return res.status(400).json({ message: 'Worksheet HTML is required.' });
    }

    const worksheet = worksheets[index];

    const bucketName = getBucketName();
    const s3Client = getS3Client();

    // Re-upload HTML
    await s3Client.send(new PutObjectCommand({
      Bucket: bucketName,
      Key: worksheet.s3HtmlKey,
      Body: html,
      ContentType: 'text/html; charset=utf-8',
      CacheControl: 'no-cache',
    }));

    // Re-generate and upload PDF
    let pdfUploaded = false;
    try {
      const pdfBuffer = await generatePDFFromHTML(html);
      const pdfKey = worksheet.s3PdfKey || worksheet.s3HtmlKey.replace(/\.html$/, '.pdf');
      await s3Client.send(new PutObjectCommand({
        Bucket: bucketName,
        Key: pdfKey,
        Body: pdfBuffer,
        ContentType: 'application/pdf',
        CacheControl: 'no-cache',
      }));
      worksheet.s3PdfKey = pdfKey;
      pdfUploaded = true;
    } catch (pdfError) {
      console.error('PDF re-generation failed:', pdfError.message);
    }

    worksheet.updatedAt = new Date().toISOString();
    worksheets[index] = worksheet;
    saveWorksheets(worksheets);

    res.json({
      message: pdfUploaded
        ? 'Worksheet updated (HTML + PDF).'
        : 'Worksheet HTML updated. PDF re-generation failed.',
      worksheet,
    });
  } catch (error) {
    console.error('Worksheet update failed:', error);
    res.status(500).json({ message: 'Failed to update worksheet.' });
  }
});

// ─── DELETE /api/worksheets/:id — Delete worksheet (owner only)

router.delete('/:id', requireAuth, async (req, res) => {
  try {
    const worksheets = loadWorksheets();
    const index = worksheets.findIndex((w) => w.id === req.params.id);

    if (index === -1) {
      return res.status(404).json({ message: 'Worksheet not found.' });
    }

    if (worksheets[index].ownerId !== req.user.id) {
      return res.status(403).json({ message: 'You can only delete your own worksheets.' });
    }

    const worksheet = worksheets[index];

    const bucketName = getBucketName();
    const s3Client = getS3Client();

    // Delete from S3
    if (bucketName) {
      console.log(`Deleting S3 objects: ${worksheet.s3HtmlKey}, ${worksheet.s3PdfKey || '(no PDF)'}`);

      const deletePromises = [
        s3Client.send(new DeleteObjectCommand({
          Bucket: bucketName,
          Key: worksheet.s3HtmlKey,
        })).then(() => console.log(`  ✓ Deleted HTML: ${worksheet.s3HtmlKey}`))
          .catch((err) => console.error(`  ✗ Failed to delete HTML: ${err.message}`)),
      ];

      if (worksheet.s3PdfKey) {
        deletePromises.push(
          s3Client.send(new DeleteObjectCommand({
            Bucket: bucketName,
            Key: worksheet.s3PdfKey,
          })).then(() => console.log(`  ✓ Deleted PDF: ${worksheet.s3PdfKey}`))
            .catch((err) => console.error(`  ✗ Failed to delete PDF: ${err.message}`)),
        );
      }

      await Promise.allSettled(deletePromises);
    } else {
      console.warn('AWS_S3_BUCKET not configured — skipping S3 deletion.');
    }

    // Remove from local storage
    worksheets.splice(index, 1);
    saveWorksheets(worksheets);

    res.json({ message: 'Worksheet deleted successfully.' });
  } catch (error) {
    console.error('Worksheet deletion failed:', error);
    res.status(500).json({ message: 'Failed to delete worksheet.' });
  }
});

export default router;
