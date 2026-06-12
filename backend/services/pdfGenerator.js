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
 *
 * @param {string} html - Full HTML document string
 * @returns {Promise<Buffer>} PDF as a Buffer
 */
export async function generatePDFFromHTML(html) {
  const browser = await getBrowser();
  const page = await browser.newPage();

  try {
    // Inject Base64 images directly into the HTML so Puppeteer doesn't need to resolve local relative paths
    let processedHtml = html;
    
    const logoBase64 = getBase64Image('logo.jpg', 'image/jpeg');
    if (logoBase64) {
      processedHtml = processedHtml.replace(/src=["']\/?logo\.jpg["']/g, `src="${logoBase64}"`);
    }

    const watermarkBase64 = getBase64Image('watermark.svg', 'image/svg\\+xml');
    if (watermarkBase64) {
      processedHtml = processedHtml.replace(/src=["']\/?watermark\.svg["']/g, `src="${watermarkBase64}"`);
    }

    // Set content and wait for fonts/images to load
    await page.setContent(processedHtml, {
      waitUntil: ['networkidle0', 'domcontentloaded'],
      timeout: 30000,
    });

    // Wait a bit extra for web fonts
    await page.evaluate(() => document.fonts?.ready);
    await new Promise((r) => setTimeout(r, 500));

    // Force print layout to measure natural height correctly
    await page.emulateMediaType('print');

    // Dynamic scale-to-fit logic (matches frontend ExportModal)
    await page.evaluate(() => {
      const pageEl = document.querySelector('.ws-page');
      if (!pageEl) return;

      // Temporarily allow natural height to measure
      pageEl.style.setProperty('height', 'auto', 'important');
      pageEl.style.setProperty('max-height', 'none', 'important');
      const wsBody = document.querySelector('.ws-body');
      if (wsBody) wsBody.style.setProperty('overflow', 'visible', 'important');

      const naturalHeight = pageEl.scrollHeight;
      const A4_HEIGHT_PX = 297 * (96 / 25.4); // ~1122.5px
      
      let scaleFactor = 1;
      if (naturalHeight > A4_HEIGHT_PX) {
        scaleFactor = Math.max(A4_HEIGHT_PX / naturalHeight, 0.5);
      }

      // Inject exact-fit A4 styling and scale factor
      const style = document.createElement('style');
      style.innerHTML = `
        @media print {
          html { overflow: hidden !important; }
          body {
            zoom: ${scaleFactor} !important;
            width: ${210 / scaleFactor}mm !important;
            height: ${297 / scaleFactor}mm !important;
            overflow: hidden !important;
            background: white !important;
          }
          .ws-page {
            width: ${210 / scaleFactor}mm !important;
            height: ${297 / scaleFactor}mm !important;
            max-height: ${297 / scaleFactor}mm !important;
            display: flex !important;
            flex-direction: column !important;
            overflow: hidden !important;
            margin: 0 !important;
            box-shadow: none !important;
          }
          .ws-header { flex-shrink: 0 !important; }
          .ws-body { flex: 1 1 auto !important; min-height: 0 !important; overflow: hidden !important; }
          .ws-footer { flex-shrink: 0 !important; margin-top: auto !important; width: 100% !important; }
          .ws-vertical-copyright, .vertical-copyright { left: -170px !important; }
        }
      `;
      document.head.appendChild(style);
    });

    // Generate PDF — exact A4 with no extra margins
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
