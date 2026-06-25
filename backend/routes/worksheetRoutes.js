import { Router } from 'express';
import { S3Client, PutObjectCommand, DeleteObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';
import { randomUUID } from 'crypto';
import { requireAuth } from '../middleware/authMiddleware.js';
import { generatePDFFromHTML } from '../services/pdfGenerator.js';
import { getPool } from '../services/db.js';

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

/** Convert MySQL row (snake_case) to API response (camelCase) */
function toApiWorksheet(row, requestUserId) {
  return {
    id: row.id,
    fileName: row.file_name,
    activityName: row.activity_name,
    activityFolder: row.activity_folder,
    s3HtmlKey: row.s3_html_key,
    s3PdfKey: row.s3_pdf_key,
    ownerId: row.owner_id,
    ownerEmail: row.owner_email,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    isOwner: row.owner_id === requestUserId,
  };
}

// ─── POST /api/worksheets/generate-pdf — Generate Letter PDF download ──

router.post('/generate-pdf', requireAuth, async (req, res) => {
  try {
    const html = typeof req.body?.html === 'string' ? req.body.html.trim() : '';
    if (!html) {
      return res.status(400).json({ message: 'Worksheet HTML is required.' });
    }

    const fileName = buildFileName(req.body?.fileName || 'worksheet');
    const pdfBuffer = await generatePDFFromHTML(html);

    res.set({
      'Content-Type': 'application/pdf',
      'Content-Disposition': `attachment; filename="${fileName}.pdf"`,
      'Content-Length': pdfBuffer.length,
    });
    res.send(pdfBuffer);
  } catch (error) {
    console.error('PDF generation failed:', error);
    res.status(500).json({ message: 'Failed to generate PDF.', error: error.message });
  }
});

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

    // 3. Save worksheet metadata to MySQL
    const pool = getPool();
    const worksheetId = randomUUID();

    await pool.execute(
      `INSERT INTO worksheets (id, file_name, activity_name, activity_folder, s3_html_key, s3_pdf_key, owner_id, owner_email)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [worksheetId, rawFileName, activityName.trim(), activityFolder, htmlKey, pdfUploaded ? pdfKey : null, req.user.id, req.user.email]
    );

    const worksheetRecord = {
      id: worksheetId,
      fileName: rawFileName,
      activityName: activityName.trim(),
      activityFolder,
      s3HtmlKey: htmlKey,
      s3PdfKey: pdfUploaded ? pdfKey : null,
      ownerId: req.user.id,
      ownerEmail: req.user.email,
      isOwner: true,
    };

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

router.get('/', requireAuth, async (req, res) => {
  try {
    const pool = getPool();
    const [rows] = await pool.execute('SELECT * FROM worksheets ORDER BY created_at DESC');

    const worksheets = rows.map((row) => toApiWorksheet(row, req.user.id));

    res.json({ worksheets });
  } catch (error) {
    console.error('Failed to list worksheets:', error);
    res.status(500).json({ message: 'Failed to load worksheets.' });
  }
});

// ─── GET /api/worksheets/:id — Get single worksheet ────────

router.get('/:id', requireAuth, async (req, res) => {
  try {
    const pool = getPool();
    const [rows] = await pool.execute('SELECT * FROM worksheets WHERE id = ?', [req.params.id]);

    if (rows.length === 0) {
      return res.status(404).json({ message: 'Worksheet not found.' });
    }

    res.json({ worksheet: toApiWorksheet(rows[0], req.user.id) });
  } catch (error) {
    console.error('Failed to get worksheet:', error);
    res.status(500).json({ message: 'Failed to load worksheet.' });
  }
});

// ─── GET /api/worksheets/:id/content — Fetch HTML from S3 ──

router.get('/:id/content', requireAuth, async (req, res) => {
  try {
    const pool = getPool();
    const [rows] = await pool.execute('SELECT * FROM worksheets WHERE id = ?', [req.params.id]);

    if (rows.length === 0) {
      return res.status(404).json({ message: 'Worksheet not found.' });
    }

    const worksheet = rows[0];
    const bucketName = getBucketName();
    const s3Client = getS3Client();

    if (!bucketName) {
      return res.status(500).json({ message: 'AWS_S3_BUCKET is not configured.' });
    }

    let html;
    try {
      const response = await s3Client.send(new GetObjectCommand({
        Bucket: bucketName,
        Key: worksheet.s3_html_key,
      }));

      const chunks = [];
      for await (const chunk of response.Body) {
        chunks.push(chunk);
      }
      html = Buffer.concat(chunks).toString('utf-8');
    } catch (s3Err) {
      if (s3Err.Code === 'NoSuchKey' || s3Err.name === 'NoSuchKey') {
        // S3 file was deleted — clean up the stale DB record
        await pool.execute('DELETE FROM worksheets WHERE id = ?', [req.params.id]);
        return res.status(404).json({
          message: 'This worksheet was deleted from storage. The record has been cleaned up.',
        });
      }
      throw s3Err; // Re-throw other S3 errors
    }

    res.json({
      worksheet: toApiWorksheet(worksheet, req.user.id),
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
    const pool = getPool();
    const [rows] = await pool.execute('SELECT * FROM worksheets WHERE id = ?', [req.params.id]);

    if (rows.length === 0) {
      return res.status(404).json({ message: 'Worksheet not found.' });
    }

    const worksheet = rows[0];

    if (worksheet.owner_id !== req.user.id) {
      return res.status(403).json({ message: 'You can only update your own worksheets.' });
    }

    const html = typeof req.body?.html === 'string' ? req.body.html.trim() : '';
    if (!html) {
      return res.status(400).json({ message: 'Worksheet HTML is required.' });
    }

    const bucketName = getBucketName();
    const s3Client = getS3Client();

    // Re-upload HTML
    await s3Client.send(new PutObjectCommand({
      Bucket: bucketName,
      Key: worksheet.s3_html_key,
      Body: html,
      ContentType: 'text/html; charset=utf-8',
      CacheControl: 'no-cache',
    }));

    // Re-generate and upload PDF
    let pdfUploaded = false;
    try {
      const pdfBuffer = await generatePDFFromHTML(html);
      const pdfKey = worksheet.s3_pdf_key || worksheet.s3_html_key.replace(/\.html$/, '.pdf');
      await s3Client.send(new PutObjectCommand({
        Bucket: bucketName,
        Key: pdfKey,
        Body: pdfBuffer,
        ContentType: 'application/pdf',
        CacheControl: 'no-cache',
      }));
      await pool.execute('UPDATE worksheets SET s3_pdf_key = ? WHERE id = ?', [pdfKey, worksheet.id]);
      pdfUploaded = true;
    } catch (pdfError) {
      console.error('PDF re-generation failed:', pdfError.message);
    }

    // Update timestamp
    await pool.execute('UPDATE worksheets SET updated_at = NOW() WHERE id = ?', [worksheet.id]);

    // Re-fetch updated record
    const [updated] = await pool.execute('SELECT * FROM worksheets WHERE id = ?', [worksheet.id]);

    res.json({
      message: pdfUploaded
        ? 'Worksheet updated (HTML + PDF).'
        : 'Worksheet HTML updated. PDF re-generation failed.',
      worksheet: toApiWorksheet(updated[0], req.user.id),
    });
  } catch (error) {
    console.error('Worksheet update failed:', error);
    res.status(500).json({ message: 'Failed to update worksheet.' });
  }
});

// ─── DELETE /api/worksheets/:id — Delete worksheet (owner only)

router.delete('/:id', requireAuth, async (req, res) => {
  try {
    const pool = getPool();
    const [rows] = await pool.execute('SELECT * FROM worksheets WHERE id = ?', [req.params.id]);

    if (rows.length === 0) {
      return res.status(404).json({ message: 'Worksheet not found.' });
    }

    const worksheet = rows[0];

    if (worksheet.owner_id !== req.user.id) {
      return res.status(403).json({ message: 'You can only delete your own worksheets.' });
    }

    const bucketName = getBucketName();
    const s3Client = getS3Client();

    // Delete from S3
    if (bucketName) {
      console.log(`Deleting S3 objects: ${worksheet.s3_html_key}, ${worksheet.s3_pdf_key || '(no PDF)'}`);

      const deletePromises = [
        s3Client.send(new DeleteObjectCommand({
          Bucket: bucketName,
          Key: worksheet.s3_html_key,
        })).then(() => console.log(`  ✓ Deleted HTML: ${worksheet.s3_html_key}`))
          .catch((err) => console.error(`  ✗ Failed to delete HTML: ${err.message}`)),
      ];

      if (worksheet.s3_pdf_key) {
        deletePromises.push(
          s3Client.send(new DeleteObjectCommand({
            Bucket: bucketName,
            Key: worksheet.s3_pdf_key,
          })).then(() => console.log(`  ✓ Deleted PDF: ${worksheet.s3_pdf_key}`))
            .catch((err) => console.error(`  ✗ Failed to delete PDF: ${err.message}`)),
        );
      }

      await Promise.allSettled(deletePromises);
    } else {
      console.warn('AWS_S3_BUCKET not configured — skipping S3 deletion.');
    }

    // Remove from MySQL
    await pool.execute('DELETE FROM worksheets WHERE id = ?', [worksheet.id]);

    res.json({ message: 'Worksheet deleted successfully.' });
  } catch (error) {
    console.error('Worksheet deletion failed:', error);
    res.status(500).json({ message: 'Failed to delete worksheet.' });
  }
});

export default router;
