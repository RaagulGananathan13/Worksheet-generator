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

    // ── Step 2: Set viewport to exact A4 dimensions ──
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

    // ── Step 5: Remove ALL @page CSS rules from HTML ──
    // @page rules in CSS conflict with Puppeteer's page.pdf() API.
    // Puppeteer's format:'A4' must be the sole authority on page size.
    await page.evaluate(() => {
      // Remove @page rules from all stylesheets
      for (const sheet of document.styleSheets) {
        try {
          const rules = sheet.cssRules || sheet.rules;
          for (let i = rules.length - 1; i >= 0; i--) {
            if (rules[i].type === CSSRule.PAGE_RULE) {
              sheet.deleteRule(i);
            }
          }
        } catch (e) { /* cross-origin stylesheets — ignore */ }
      }
    });

    // ── Step 6: Inject layout CSS + measure + scale ──
    await page.evaluate(() => {
      const pageEl = document.querySelector('.ws-page') || document.querySelector('.page');
      if (!pageEl) return;

      // --- Inject layout CSS (NO @page — Puppeteer API handles that) ---
      const baseStyle = document.createElement('style');
      baseStyle.id = 'ws-pdf-base';
      baseStyle.innerHTML = `
        *, *::before, *::after { box-sizing: border-box; }
        html, body {
          width: 210mm;
          height: 297mm;
          margin: 0;
          padding: 0;
          overflow: hidden;
          background: white;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }
        .ws-page, .page {
          width: 210mm !important;
          height: 297mm !important;
          min-height: 297mm !important;
          max-height: 297mm !important;
          margin: 0 !important;
          padding: 0 !important;
          box-shadow: none !important;
          border: none !important;
          display: flex !important;
          flex-direction: column !important;
          overflow: hidden !important;
          transform-origin: top left;
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
          margin-top: auto !important;
        }
        .ws-vertical-copyright, .vertical-copyright {
          left: -193px !important;
        }
      `;
      document.head.appendChild(baseStyle);

      // Force layout recalc with base CSS
      void pageEl.offsetHeight;

      // --- Measure A4 height dynamically ---
      const measureDiv = document.createElement('div');
      measureDiv.style.cssText = 'position:absolute;width:210mm;height:297mm;visibility:hidden;pointer-events:none;';
      document.body.appendChild(measureDiv);
      const A4_HEIGHT_PX = measureDiv.offsetHeight;
      document.body.removeChild(measureDiv);

      // --- Measure natural content height ---
      pageEl.style.setProperty('height', 'auto', 'important');
      pageEl.style.setProperty('max-height', 'none', 'important');
      pageEl.style.setProperty('min-height', '0', 'important');
      const wsBody = pageEl.querySelector('.ws-body') || pageEl.querySelector('.body');
      if (wsBody) {
        wsBody.style.setProperty('overflow', 'visible', 'important');
        wsBody.style.setProperty('flex', 'none', 'important');
      }

      void pageEl.offsetHeight;
      const naturalHeight = pageEl.scrollHeight;

      // --- Remove temporary measurement styles ---
      pageEl.style.removeProperty('height');
      pageEl.style.removeProperty('max-height');
      pageEl.style.removeProperty('min-height');
      if (wsBody) {
        wsBody.style.removeProperty('overflow');
        wsBody.style.removeProperty('flex');
      }

      // --- Calculate scale factor ---
      let scaleFactor = 1;
      if (naturalHeight > A4_HEIGHT_PX) {
        scaleFactor = Math.max(A4_HEIGHT_PX / naturalHeight, 0.5);
      }

      // --- Apply scale using CSS transform (NOT zoom) ---
      if (scaleFactor < 1) {
        const scaleStyle = document.createElement('style');
        scaleStyle.id = 'ws-pdf-scale';
        scaleStyle.innerHTML = `
          .ws-page, .page {
            transform: scale(${scaleFactor}) !important;
            transform-origin: top left !important;
            width: ${210 / scaleFactor}mm !important;
            height: ${297 / scaleFactor}mm !important;
            max-height: ${297 / scaleFactor}mm !important;
          }
        `;
        document.head.appendChild(scaleStyle);
      }
    });

    // ── Step 7: Generate PDF — format:'A4' = exactly 595×842pt ──
    // DO NOT use width/height with mm units (Chromium can misparse them).
    // DO NOT use preferCSSPageSize:true (CSS @page overrides to Letter).
    // format:'A4' is the ONLY reliable way to guarantee 595×842pt output.
    const pdfBuffer = await page.pdf({
      format: 'A4',
      printBackground: true,
      margin: { top: '0', right: '0', bottom: '0', left: '0' },
      preferCSSPageSize: false,
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
