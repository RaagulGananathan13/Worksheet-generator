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
 *   1. Set viewport to Letter width (216mm ≈ 816px at 96dpi)
 *   2. Inject base Letter export CSS (same as frontend ws-export-fix)
 *   3. Measure natural content height
 *   4. Calculate zoom scale factor if content overflows Letter
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

    // ── Step 1b: Inject Google Fonts for consistent rendering on all environments ──
    // On localhost (Windows), 'Times New Roman' and 'Poppins' may be available locally.
    // On AWS (Linux), these fonts are NOT installed — headless Chromium falls back to
    // generic serif/sans-serif which looks completely different.
    // Fix: Inject Google Fonts imports + @font-face aliases BEFORE rendering.
    const fontInjection = `
      <style id="ws-pdf-fonts">
        /* Import Google Fonts — these load reliably in headless Chromium */
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&family=Tinos:ital,wght@0,400;0,700;1,400;1,700&family=Noto+Sans+Sinhala:wght@300;400;500;600;700&display=block');

        /* Map 'Times New Roman' and 'Times' to 'Tinos' (metrically identical Google Font)
           so that CSS rules referencing 'Times New Roman' work on Linux without the font installed */
        @font-face {
          font-family: 'Times New Roman';
          src: local('Times New Roman'), local('Tinos');
          font-weight: 400;
          font-style: normal;
        }
        @font-face {
          font-family: 'Times New Roman';
          src: local('Times New Roman'), local('Tinos');
          font-weight: 700;
          font-style: normal;
        }
        @font-face {
          font-family: 'Times';
          src: local('Times'), local('Tinos');
          font-weight: 400;
          font-style: normal;
        }

        /* Ensure footer and copyright always use Tinos as reliable fallback */
        .ws-footer, .ws-footer *, .ws-vertical-copyright {
          font-family: 'Tinos', 'Times New Roman', Times, serif !important;
        }
        .ws-eng-text {
          font-family: 'Tinos', 'Times New Roman', Times, serif !important;
        }
        .ws-footer-info {
          font-size: 9pt !important;
          font-weight: 400 !important;
        }
        .ws-vertical-copyright {
          font-size: 7pt !important;
          font-weight: 400 !important;
        }

        /* Ensure header always uses Poppins loaded from Google Fonts */
        .ws-header, .ws-header * {
          font-family: 'Poppins', Arial, sans-serif !important;
        }
        .ws-activity-id {
          font-size: 15px !important;
          font-weight: 700 !important;
        }
        .ws-activity-title {
          font-size: 14px !important;
          font-weight: 700 !important;
        }
        .ws-form-row {
          font-size: 12px !important;
        }
      </style>
    `;

    // Inject right after <head> tag so fonts load first
    if (processedHtml.includes('</head>')) {
      processedHtml = processedHtml.replace('</head>', fontInjection + '</head>');
    } else if (processedHtml.includes('<body')) {
      processedHtml = processedHtml.replace('<body', fontInjection + '<body');
    }

    // ── Step 2: Set viewport to exact Letter dimensions (matches frontend iframe width:216mm) ──
    await page.setViewport({
      width: 816,   // 216mm at 96dpi
      height: 1054, // 279mm at 96dpi
      deviceScaleFactor: 1,
    });

    // ── Step 3: Load content and wait for all resources ──
    await page.setContent(processedHtml, {
      waitUntil: ['networkidle0', 'domcontentloaded'],
      timeout: 30000,
    });

    // Wait for web fonts — increased timeout for AWS network latency
    try {
      await page.evaluate(() => {
        return new Promise((resolve) => {
          if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(() => resolve());
          } else {
            resolve();
          }
        });
      });
    } catch (e) {
      // Font loading timeout — continue anyway
      console.warn('Font loading wait timed out, continuing with available fonts');
    }
    // Extra settle time for fonts to fully render (critical on slow AWS networks)
    await new Promise((r) => setTimeout(r, 1500));

    // ── Step 4: Emulate print media for correct CSS rules ──
    await page.emulateMediaType('print');

    // ── Step 5: Strip @page CSS rules + inject base Letter layout CSS ──
    // Puppeteer's format:'Letter' with preferCSSPageSize:false is the sole authority
    // on page size. Remove any @page rules that could conflict.
    await page.evaluate(() => {
      // Remove @page rules from all stylesheets to prevent conflicts
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

      // Also neutralize any @media print rules that break flex layout
      for (const sheet of document.styleSheets) {
        try {
          const rules = sheet.cssRules || sheet.rules;
          for (let i = rules.length - 1; i >= 0; i--) {
            if (rules[i].type === CSSRule.MEDIA_RULE &&
                rules[i].conditionText && rules[i].conditionText.includes('print')) {
              sheet.deleteRule(i);
            }
          }
        } catch (e) { /* cross-origin — ignore */ }
      }

      // Find the page container (supports both new .ws-page and old .page class)
      const pageEl = document.querySelector('.ws-page') || document.querySelector('.page');
      if (!pageEl) return;

      // --- Inject base Letter layout CSS (no @page — Puppeteer API handles page size) ---
      const baseStyle = document.createElement('style');
      baseStyle.id = 'ws-pdf-base';
      baseStyle.innerHTML = `
        *, *::before, *::after { box-sizing: border-box; }
        html {
          width: 216mm; height: 279mm;
          margin: 0; padding: 0;
          overflow: hidden;
        }
        body {
          width: 216mm; height: 279mm;
          margin: 0; padding: 0;
          background: white;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
          overflow: hidden;
        }
        /* Flex column layout — pins footer to bottom */
        .ws-page, .page {
          width: 216mm !important;
          height: 279mm !important;
          min-height: 0 !important;
          max-height: 279mm !important;
          margin: 0 !important;
          padding: 0 !important;
          box-shadow: none !important;
          border: none !important;
          display: flex !important;
          flex-direction: column !important;
          overflow: hidden !important;
          position: relative !important;
        }
        .ws-header, .header {
          flex-shrink: 0 !important;
        }
        .ws-body, .body {
          flex: 1 1 auto !important;
          min-height: 0 !important;
          overflow: hidden !important;
        }
        .ws-footer, .footer {
          flex-shrink: 0 !important;
          width: 100% !important;
          text-align: center !important;
          padding: 0 12mm 15px 12mm !important;
          margin-top: auto !important;
          color: #111 !important;
          box-sizing: border-box !important;
        }
        .ws-footer-copyright, .footer-copyright {
          display: none !important;
        }
        .ws-footer-info, .footer-info {
          font-size: 9pt !important;
          display: flex !important;
          justify-content: space-between !important;
          width: 100% !important;
          align-items: center !important;
          font-weight: 400 !important;
        }
        .ws-footer-info span, .footer-info span {
          white-space: nowrap !important;
        }
        .ws-vertical-copyright, .vertical-copyright {
          position: absolute !important;
          left: -193px !important;
          width: 400px !important;
          top: 50% !important;
          text-align: center !important;
          transform: translateY(-50%) rotate(90deg) !important;
          font-size: 7pt !important;
          font-weight: 400 !important;
          color: #111 !important;
          pointer-events: none !important;
          white-space: nowrap !important;
        }
      `;
      document.head.appendChild(baseStyle);

      // Force layout recalc with base CSS applied
      void pageEl.offsetHeight;

      // --- Measure natural content height ---
      // Temporarily allow the page to expand so we can measure true content height
      pageEl.style.setProperty('height', 'auto', 'important');
      pageEl.style.setProperty('max-height', 'none', 'important');
      const wsBody = pageEl.querySelector('.ws-body') || pageEl.querySelector('.body');
      if (wsBody) wsBody.style.setProperty('overflow', 'visible', 'important');

      // Force layout recalc
      void pageEl.offsetHeight;

      const naturalHeight = pageEl.scrollHeight;
      const LETTER_HEIGHT_PX = 279 * (96 / 25.4); // ≈ 1053.54px

      // --- CRITICAL: Remove temporary inline styles so CSS rules take over ---
      pageEl.style.removeProperty('height');
      pageEl.style.removeProperty('max-height');
      if (wsBody) wsBody.style.removeProperty('overflow');

      // --- Calculate scale factor ---
      let scaleFactor = 1;
      if (naturalHeight > LETTER_HEIGHT_PX) {
        scaleFactor = Math.max(LETTER_HEIGHT_PX / naturalHeight, 0.5);
      }

      // --- Inject scale-to-fit CSS using transform (NOT zoom) ---
      // transform:scale is spec-compliant and Puppeteer renders it identically
      // to the screen preview, unlike the non-standard zoom property.
      if (scaleFactor < 1) {
        const scaleStyle = document.createElement('style');
        scaleStyle.id = 'ws-pdf-scale';
        scaleStyle.innerHTML = `
          .ws-page, .page {
            /* Use transform:scale for content shrinking — keeps all child
               positions proportional (images, footer, copyright all stay put) */
            transform: scale(${scaleFactor}) !important;
            transform-origin: top left !important;
            /* Expand the layout box so scaled content fills the Letter page */
            width: ${216 / scaleFactor}mm !important;
            height: ${279 / scaleFactor}mm !important;
            max-height: ${279 / scaleFactor}mm !important;
            /* Flex must stay for footer pinning */
            display: flex !important;
            flex-direction: column !important;
            overflow: hidden !important;
          }
          .ws-body, .body {
            flex: 1 1 auto !important;
            min-height: 0 !important;
            overflow: hidden !important;
          }
          .ws-footer, .footer {
            flex-shrink: 0 !important;
            width: 100% !important;
            text-align: center !important;
            padding: 0 12mm 15px 12mm !important;
            margin-top: auto !important;
            color: #111 !important;
          }
          .ws-footer-copyright, .footer-copyright {
            display: none !important;
          }
          .ws-footer-info, .footer-info {
            font-size: 9pt !important;
            display: flex !important;
            justify-content: space-between !important;
            width: 100% !important;
            align-items: center !important;
            font-weight: 400 !important;
          }
          .ws-footer-info span, .footer-info span {
            white-space: nowrap !important;
          }
        `;
        document.head.appendChild(scaleStyle);
      }
    });

    // ── Step 6: Generate PDF ──
    // format:'Letter' = exactly 612×792pt (216mm × 279mm)
    // preferCSSPageSize:false ensures Puppeteer's format is the sole authority
    const pdfBuffer = await page.pdf({
      format: 'Letter',
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
