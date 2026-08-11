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

    // ── Step 1b: Inject Google Fonts <link> tags for consistent rendering on all environments ──
    // ROOT CAUSE: On localhost (Windows), 'Times New Roman' is a system font and the OS provides
    // Sinhala fallback fonts (e.g., 'Iskoola Pota'). On AWS (Linux), NEITHER exists — headless
    // Chromium falls back to generic serif/sans-serif which looks completely different.
    //
    // FIX: Inject <link> tags (NOT @import which is unreliable in headless Chromium) for:
    //   - Poppins: Header font
    //   - Tinos: Metrically identical to Times New Roman (footer/copyright)
    //   - Noto Sans Sinhala: For Sinhala character rendering (no system Sinhala fonts on Linux)

    // Detect if this is a Sinhala worksheet
    const isSinhala = processedHtml.includes('Noto Sans Sinhala') || 
                      processedHtml.includes('Noto+Sans+Sinhala') ||
                      processedHtml.includes('ws-eng-text');

    const fontLinks = `
      <link rel="preconnect" href="https://fonts.googleapis.com">
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
      <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&family=Tinos:ital,wght@0,400;0,700;1,400;1,700&family=Noto+Sans+Sinhala:wght@300;400;500;600;700&display=block" rel="stylesheet">
    `;

    const fontOverrides = `
      <style id="ws-pdf-font-overrides">
        /* ── Footer & Copyright: Use Tinos (Google's TNR equivalent) ── */
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

        /* ── Header: Poppins + Sinhala fallback ── */
        .ws-header, .ws-header * {
          font-family: 'Poppins', ${isSinhala ? "'Noto Sans Sinhala', " : ""}Arial, sans-serif !important;
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

        ${isSinhala ? `
        /* ── Sinhala: Ensure Noto Sans Sinhala is in all font stacks ── */
        .ws-footer-info span:not(.ws-eng-text) {
          font-family: 'Noto Sans Sinhala', 'Tinos', 'Times New Roman', serif !important;
        }
        .ws-vertical-copyright {
          font-family: 'Noto Sans Sinhala', 'Tinos', 'Times New Roman', serif !important;
        }
        body {
          font-family: 'Noto Sans Sinhala', 'Poppins', Arial, sans-serif !important;
        }
        ` : ''}
      </style>
    `;

    // Inject <link> tags BEFORE </head> — <link> is more reliable than @import in headless Chromium
    if (processedHtml.includes('</head>')) {
      processedHtml = processedHtml.replace('</head>', fontLinks + fontOverrides + '</head>');
    } else if (processedHtml.includes('<body')) {
      processedHtml = processedHtml.replace('<body', fontLinks + fontOverrides + '<body');
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

    // ── Step 3b: Robust font loading — wait until specific fonts are actually available ──
    // document.fonts.ready resolves too early on some systems. Instead, we actively
    // check that the required font families have loaded before proceeding.
    const requiredFonts = ['Poppins', 'Tinos'];
    if (isSinhala) requiredFonts.push('Noto Sans Sinhala');

    try {
      await page.evaluate(async (fonts) => {
        // Wait for the FontFaceSet to be ready first
        if (document.fonts && document.fonts.ready) {
          await document.fonts.ready;
        }

        // Then actively check each font family with a timeout
        const checkFont = (family) => {
          return new Promise((resolve) => {
            const maxAttempts = 20; // 20 × 500ms = 10 seconds max per font
            let attempts = 0;
            const check = () => {
              if (document.fonts && document.fonts.check(`16px "${family}"`)) {
                resolve(true);
              } else if (attempts++ < maxAttempts) {
                setTimeout(check, 500);
              } else {
                console.warn(`Font "${family}" did not load within timeout`);
                resolve(false);
              }
            };
            check();
          });
        };

        await Promise.all(fonts.map(f => checkFont(f)));
      }, requiredFonts);
    } catch (e) {
      console.warn('Font loading check failed, continuing with available fonts:', e.message);
    }

    // Final settle time — let the renderer apply fonts to all glyphs
    await new Promise((r) => setTimeout(r, 1000));

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
