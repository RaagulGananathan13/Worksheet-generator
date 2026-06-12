import puppeteer from 'puppeteer';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

let browserInstance = null;

/**
 * Get or launch a shared Puppeteer browser instance.
 * Reusing the browser avoids cold-start latency on each PDF generation.
 */
async function getBrowser() {
  if (browserInstance && browserInstance.connected) {
    return browserInstance;
  }
  browserInstance = await puppeteer.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
    ],
  });
  return browserInstance;
}

/**
 * Helper to convert local images to Base64 Data URIs
 */
function getBase64Image(fileName, mimeType) {
  try {
    const filePath = join(__dirname, '..', '..', 'frontend', 'public', fileName);
    const fileData = readFileSync(filePath);
    return `data:${mimeType};base64,${fileData.toString('base64')}`;
  } catch (err) {
    console.error(`Failed to load image for PDF: ${fileName}`, err.message);
    return null;
  }
}

/**
 * Convert an HTML string to a PDF buffer.
 * Mirrors the frontend ExportModal's dynamic scale-to-fit logic exactly:
 *   1. Set viewport to A4 width (210mm ≈ 794px at 96dpi)
 *   2. Inject base A4 export CSS (same as frontend ws-export-fix)
 *   3. Measure natural content height
 *   4. Calculate zoom scale factor if content overflows A4
 *   5. Inject scale CSS and generate PDF
 *
 * @param {string} html - Full HTML document string
 * @returns {Promise<Buffer>} PDF as a Buffer
 */
export async function generatePDFFromHTML(html) {
  const browser = await getBrowser();
  const page = await browser.newPage();

  try {
    // ── Step 1: Inline images as Base64 Data URIs ──
    let processedHtml = html;

    const logoBase64 = getBase64Image('logo.jpg', 'image/jpeg');
    if (logoBase64) {
      processedHtml = processedHtml.replace(/src=["']\/?logo\.jpg["']/g, `src="${logoBase64}"`);
    }

    const watermarkBase64 = getBase64Image('watermark.svg', 'image/svg+xml');
    if (watermarkBase64) {
      processedHtml = processedHtml.replace(/src=["']\/?watermark\.svg["']/g, `src="${watermarkBase64}"`);
    }

    // ── Step 2: Set viewport to exact A4 dimensions (matches frontend iframe width:210mm) ──
    await page.setViewport({
      width: 794,   // 210mm at 96dpi
      height: 1123, // 297mm at 96dpi
      deviceScaleFactor: 1,
    });

    // ── Step 3: Load content and wait for all resources ──
    await page.setContent(processedHtml, {
      waitUntil: ['networkidle0', 'domcontentloaded'],
      timeout: 30000,
    });

    // Wait for web fonts
    await page.evaluate(() => document.fonts?.ready);
    await new Promise((r) => setTimeout(r, 500));

    // ── Step 4: Emulate print media for correct CSS rules ──
    await page.emulateMediaType('print');

    // ── Step 5: Inject base A4 CSS + measure + scale (mirrors frontend ws-export-fix exactly) ──
    await page.evaluate(() => {
      // Find the page container (supports both new .ws-page and old .page class)
      const pageEl = document.querySelector('.ws-page') || document.querySelector('.page');
      if (!pageEl) return;

      // --- Inject base A4 export CSS (identical to frontend ws-export-fix) ---
      const baseStyle = document.createElement('style');
      baseStyle.id = 'ws-pdf-base';
      baseStyle.innerHTML = `
        *, *::before, *::after { box-sizing: border-box; }
        @page { size: A4; margin: 0; }
        html {
          width: 210mm; height: 297mm;
          margin: 0; padding: 0;
          overflow: hidden;
        }
        body {
          width: 210mm; height: 297mm;
          margin: 0; padding: 0;
          background: white;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
          overflow: hidden;
        }
        .ws-page, .page {
          width: 210mm !important;
          height: 297mm !important;
          min-height: 0 !important;
          max-height: 297mm !important;
          margin: 0 !important;
          padding: 0 !important;
          box-shadow: none !important;
          border: none !important;
          display: flex !important;
          flex-direction: column !important;
          overflow: hidden !important;
        }
        .ws-header, .header { flex-shrink: 0 !important; }
        .ws-body, .body {
          flex: 1 1 auto !important;
          min-height: 0 !important;
          overflow: hidden !important;
        }
        .ws-footer, .footer {
          flex-shrink: 0 !important;
          width: 100% !important;
          padding: 2mm 8mm 4mm 8mm !important;
          margin-top: auto !important;
        }
        .ws-footer-row {
          display: flex !important;
          align-items: center !important;
          justify-content: space-between !important;
          width: 100% !important;
          font-size: 7px !important;
          gap: 4px !important;
        }
        .ws-footer-row span {
          display: inline-block !important;
          white-space: nowrap !important;
        }
        .ws-vertical-copyright, .vertical-copyright {
          left: -170px !important;
        }
      `;
      document.head.appendChild(baseStyle);

      // Force layout recalc with base CSS applied
      void pageEl.offsetHeight;

      // --- Measure natural content height ---
      pageEl.style.setProperty('height', 'auto', 'important');
      pageEl.style.setProperty('max-height', 'none', 'important');
      const wsBody = pageEl.querySelector('.ws-body') || pageEl.querySelector('.body');
      if (wsBody) wsBody.style.setProperty('overflow', 'visible', 'important');

      // Force layout recalc
      void pageEl.offsetHeight;

      const naturalHeight = pageEl.scrollHeight;
      const A4_HEIGHT_PX = 297 * (96 / 25.4); // ≈ 1122.52px

      // --- Calculate scale factor ---
      let scaleFactor = 1;
      if (naturalHeight > A4_HEIGHT_PX) {
        scaleFactor = Math.max(A4_HEIGHT_PX / naturalHeight, 0.5);
      }

      // --- Inject scale-to-fit CSS ---
      const scaleStyle = document.createElement('style');
      scaleStyle.id = 'ws-pdf-scale';
      scaleStyle.innerHTML = `
        body {
          zoom: ${scaleFactor} !important;
          width: ${210 / scaleFactor}mm !important;
          height: ${297 / scaleFactor}mm !important;
        }
        .ws-page, .page {
          width: ${210 / scaleFactor}mm !important;
          height: ${297 / scaleFactor}mm !important;
          max-height: ${297 / scaleFactor}mm !important;
        }
      `;
      document.head.appendChild(scaleStyle);
    });

    // ── Step 6: Generate PDF ──
    const pdfBuffer = await page.pdf({
      format: 'A4',
      printBackground: true,
      margin: { top: '0', right: '0', bottom: '0', left: '0' },
      preferCSSPageSize: true,
    });

    return Buffer.from(pdfBuffer);
  } finally {
    await page.close();
  }
}

/**
 * Gracefully close the shared browser instance.
 */
export async function closeBrowser() {
  if (browserInstance) {
    await browserInstance.close();
    browserInstance = null;
  }
}
