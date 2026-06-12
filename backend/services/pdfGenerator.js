import puppeteer from 'puppeteer';

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
 * Convert an HTML string to a PDF buffer.
 *
 * @param {string} html - Full HTML document string
 * @returns {Promise<Buffer>} PDF as a Buffer
 */
export async function generatePDFFromHTML(html) {
  const browser = await getBrowser();
  const page = await browser.newPage();

  try {
    // Set content and wait for fonts/images to load
    await page.setContent(html, {
      waitUntil: ['networkidle0', 'domcontentloaded'],
      timeout: 30000,
    });

    // Wait a bit extra for web fonts
    await page.evaluate(() => document.fonts?.ready);
    await new Promise((r) => setTimeout(r, 500));

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
