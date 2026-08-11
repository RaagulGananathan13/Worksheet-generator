/**
 * Template Wrapper Engine
 * Wraps user-uploaded worksheet HTML content inside the
 * GeniusBees template (header + body + footer).
 */

const TEMPLATE_CSS = `
  *,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
  @page{size:216mm 279mm;margin:0}
  html{height:100%}
  body{
    font-family:'Poppins',Arial,sans-serif;
    background:#fff;
    margin:0;padding:0;
    height:100%;
    -webkit-print-color-adjust:exact;
    print-color-adjust:exact;
  }
  .ws-page{
    width:100%;
    min-height:100%;
    background:#fff;
    position:relative;
    display:flex;
    flex-direction:column;
    margin:0;padding:0;
    box-shadow:none;
    border:none;
    outline:none;
  }
  @media print{
    html,body{height:auto!important}
    body{background:none;margin:0;padding:0}
    /* CRITICAL: Keep flex layout in print — removing flex breaks footer pinning */
    .ws-page{margin:0;width:216mm;min-height:279mm;display:flex!important;flex-direction:column!important;overflow:hidden}
    .ws-header{break-inside:avoid;page-break-inside:avoid;flex-shrink:0!important}
    .ws-body{flex:1 1 auto!important;min-height:0!important;overflow:hidden!important}
    .ws-footer{break-inside:avoid;page-break-inside:avoid;flex-shrink:0!important;margin-top:auto!important}
    /* Keep footer-copyright hidden — matches preview (vertical sidebar handles copyright) */
    .ws-footer-copyright{display:none!important}
    /* Keep space-between — matches preview layout */
    .ws-footer-info{display:flex!important;width:100%!important;justify-content:space-between!important}
    .ws-body-content>*{break-inside:auto}
  }

  /* ═══ HEADER ═══ */
  .ws-header, .ws-header * { font-family: 'Poppins', Arial, sans-serif !important; }
  .ws-header { padding: 7mm 12mm 5mm 12mm; border-bottom: none; display: flex; gap: 15px; flex-shrink: 0; }
  .ws-header-left { width: 120px; flex-shrink: 0; display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
  .ws-header-left img { width: 140px; height: auto; display: block; margin-left: -10px; }
  .ws-grade-table { border-collapse: collapse; margin-left: 4px; }
  .ws-grade-table td { width: 40px; height: 35px; text-align: center; font-size: 18px; font-weight: 300; color: #555; border: none; }
  .ws-grade-table tr:first-child td { border-bottom: 1px solid #777; }
  .ws-grade-table td:not(:last-child) { border-right: 1px solid #777; }
  .ws-header-mid { flex: 1 !important; padding: 0 15px !important; display: flex !important; flex-direction: column !important; justify-content: center !important; overflow: hidden !important; }
  .ws-activity-id { font-size: 15px !important; font-weight: 700 !important; color: #111 !important; margin: 0 0 4px 0 !important; line-height: 1.2 !important; }
  .ws-activity-title { font-size: 14px !important; font-weight: 700 !important; color: #111 !important; margin: 0 0 16px 0 !important; line-height: 1.2 !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ws-form-fields { display: flex !important; flex-direction: column !important; gap: 8px !important; margin: 0 !important; padding: 0 !important; width: 100% !important; }
  .ws-form-row { display: flex !important; align-items: baseline !important; gap: 2px !important; font-size: 12px !important; color: #333 !important; width: 100% !important; margin: 0 !important; padding: 0 !important; line-height: 1.2 !important; }
  .ws-f-label { font-weight: 400 !important; white-space: nowrap !important; color: #333 !important; }
  .ws-f-line-dashed { flex: 1 !important; border-bottom: 1px dashed #555 !important; margin-bottom: 4px !important; min-width: 20px !important; }
  .ws-f-line-sm-dashed { width: 60px !important; border-bottom: 1px dashed #555 !important; margin-bottom: 4px !important; }
  .ws-d-line-dashed { width: 22px !important; border-bottom: 1px dashed #555 !important; margin-bottom: 4px !important; }
  .ws-d-line-y-dashed { width: 35px !important; border-bottom: 1px dashed #555 !important; margin-bottom: 4px !important; }
  .ws-d-sep { font-weight: 400 !important; margin: 0 4px !important; color: #333 !important; }
  .ws-header-right { width: 125px; flex-shrink: 0; display: flex; align-items: flex-start; justify-content: flex-end; }

  /* ═══ BODY ═══ */
  .ws-body{
    flex:1;
    position:relative;
    padding:10mm 12mm 10mm 12mm;
  }
  .ws-wm-wrap{position:absolute;inset:0;overflow:hidden;pointer-events:none;z-index:0}
  .ws-wm{
    position:absolute;width:180px;opacity:0.06;filter:grayscale(100%);
    pointer-events:none;user-select:none;transform:rotate(-15deg);
  }
  .ws-wm1{top:20%;right:12%}
  .ws-wm2{top:55%;left:8%}
  .ws-wm3{bottom:10%;right:15%}
  .ws-body-content{position:relative;z-index:1}
  /* Strip shadows/margins from user's original container */
  .ws-body-content>*{
    box-shadow:none!important;
    margin-top:0!important;
    border-radius:0!important;
  }
  .ws-body-content>div:first-child,
  .ws-body-content>section:first-child,
  .ws-body-content>main:first-child{
    margin:0!important;
    padding-top:0!important;
    box-shadow:none!important;
    border:none!important;
  }

  /* ═══ FOOTER ═══ */
  .ws-footer, .ws-footer *, .ws-vertical-copyright { font-family: 'Tinos', 'Times New Roman', Times, serif !important; }
  .ws-footer {
    width: 100% !important;
    text-align: center !important;
    padding: 0 12mm 15px 12mm !important;
    color: #111 !important;
    flex-shrink: 0 !important;
    margin-top: auto !important;
    box-sizing: border-box !important;
  }
  .ws-footer-copyright {
    display: none !important;
  }
  .ws-footer-info {
    font-size: 9pt !important;
    display: flex !important;
    justify-content: space-between !important;
    width: 100% !important;
    align-items: center !important;
    font-weight: 400 !important;
  }
  .ws-footer-info span {
    white-space: nowrap !important;
  }
  .ws-vertical-copyright {
    position: absolute;
    left: -193px;
    width: 400px;
    top: 50%;
    text-align: center;
    transform: translateY(-50%) rotate(90deg);
    font-size: 7pt;
    font-weight: 400;
    color: #111;
    pointer-events: none;
    white-space: nowrap;
  }
`;

const TEMPLATE_HEADER = `
  <div class="ws-header">
    <div class="ws-header-left">
      <img src="logo.jpg" alt="GeniusBees">
      <table class="ws-grade-table">
        <tr><td>A+</td><td>B+</td><td>C</td></tr>
        <tr><td>A</td><td>B</td><td>D</td></tr>
      </table>
    </div>
    <div class="ws-header-mid">
      <div class="ws-activity-id">Worksheet ID : 140100100001</div>
      <div class="ws-activity-title">Addition with two digit numbers</div>
      <div class="ws-form-fields">
        <div class="ws-form-row">
          <span class="ws-f-label">ID</span>
          <div class="ws-f-line-dashed"></div>
        </div>
        <div class="ws-form-row">
          <span class="ws-f-label">Name</span>
          <div class="ws-f-line-dashed"></div>
        </div>
        <div class="ws-form-row">
          <span class="ws-f-label">Date</span>
          <div class="ws-d-line-dashed"></div><span class="ws-d-sep">/</span><div class="ws-d-line-dashed"></div><span class="ws-d-sep">/</span><div class="ws-d-line-y-dashed"></div>
          <span class="ws-f-label" style="margin-left:4px">Start time</span>
          <div class="ws-f-line-dashed"></div>
          <span class="ws-f-label" style="margin-left:4px">Finish time</span>
          <div class="ws-f-line-dashed"></div>
        </div>
      </div>
    </div>
    <div class="ws-header-right"></div>
  </div>`;

const TEMPLATE_FOOTER = `
  <div class="ws-vertical-copyright">Copyright&copy; 2026 GeniusBees Inc. All rights reserved.</div>
  <div class="ws-footer">
    <div class="ws-footer-info">
      <span>www.geniusbees.com</span>
      <span>info@geniusbees.com</span>
      <span>This worksheet is for the use of registered geniusbees.com students only.</span>
    </div>
  </div>`;

/**
 * Extract just the <body> inner content from full HTML.
 * If the HTML doesn't have <body>, return as-is.
 */
function extractBodyContent(html) {
  const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  if (bodyMatch) return bodyMatch[1].trim();
  // If no body tag, check if it's a fragment
  if (!html.includes('<html') && !html.includes('<!DOCTYPE')) {
    return html.trim();
  }
  return html.trim();
}

/**
 * Extract <style> and <link> tags from <head> to preserve original CSS.
 */
function extractHeadStyles(html) {
  const styles = [];
  // Extract <style> blocks
  const styleRegex = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  let match;
  while ((match = styleRegex.exec(html)) !== null) {
    styles.push(match[0]);
  }
  // Extract <link rel="stylesheet"> tags
  const linkRegex = /<link[^>]*rel=["']stylesheet["'][^>]*\/?>/gi;
  while ((match = linkRegex.exec(html)) !== null) {
    styles.push(match[0]);
  }
  return styles.join('\n');
}

/**
 * Wrap user HTML content inside the GeniusBees template.
 * Preserves original CSS while adding template structure.
 */
export function wrapInTemplate(userHTML) {
  const bodyContent = extractBodyContent(userHTML);
  const originalStyles = extractHeadStyles(userHTML);

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GeniusBees Worksheet</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Tinos:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
<style>${TEMPLATE_CSS}</style>
${originalStyles}
</head>
<body>
<div class="ws-page">
${TEMPLATE_HEADER}
  <div class="ws-body">
    <div class="ws-wm-wrap">
      <img src="watermark.svg" class="ws-wm ws-wm1" alt="Watermark">
      <img src="watermark.svg" class="ws-wm ws-wm2" alt="Watermark">
      <img src="watermark.svg" class="ws-wm ws-wm3" alt="Watermark">
    </div>
    <div class="ws-body-content">
      ${bodyContent}
    </div>
  </div>
${TEMPLATE_FOOTER}
</div>
</body>
</html>`;
}

/**
 * Unwrap user HTML content from the GeniusBees template.
 * This is the reverse of wrapInTemplate() — given the full template-wrapped
 * document (from draftHTML), it extracts just the user's body content
 * and any user-authored styles, returning a standalone HTML string.
 *
 * This ensures editor changes (inline styles from font-size, color, etc.)
 * are reflected back in the user's source code.
 */
export function unwrapFromTemplate(wrappedHTML) {
  if (!wrappedHTML) return '';

  // Use a DOM parser to reliably extract content
  const parser = new DOMParser();
  const doc = parser.parseFromString(wrappedHTML, 'text/html');

  // 1. Extract the user's body content from .ws-body-content
  const bodyContentEl = doc.querySelector('.ws-body-content');
  if (!bodyContentEl) {
    // Fallback: if no template structure found, return body innerHTML
    return doc.body ? doc.body.innerHTML.trim() : wrappedHTML;
  }
  const userBodyHTML = bodyContentEl.innerHTML.trim();

  // 2. Extract user styles (exclude template CSS and editor injections)
  const userStyles = [];
  doc.querySelectorAll('style').forEach((styleEl) => {
    const id = styleEl.id || '';
    // Skip template and editor-injected styles
    if (id === 'ws-editor-styles' || id === 'ws-readonly-styles' ||
        id === 'ws-scale-to-fit' || id === 'ws-scale-css' ||
        id === 'ws-pdf-base' || id === 'ws-pdf-scale') {
      return;
    }
    const content = styleEl.textContent || '';
    // Skip the main template CSS (contains TEMPLATE_CSS markers)
    if (content.includes('.ws-page') && content.includes('.ws-header') &&
        content.includes('.ws-footer') && content.includes('@page')) {
      return;
    }
    // This is a user style — keep it
    userStyles.push(`<style>${content}</style>`);
  });

  // 3. Extract user stylesheet links (exclude Google Fonts Poppins from template)
  const userLinks = [];
  doc.querySelectorAll('link[rel="stylesheet"]').forEach((linkEl) => {
    const href = linkEl.getAttribute('href') || '';
    // Skip the template's Poppins font link
    if (href.includes('fonts.googleapis.com') && href.includes('Poppins') && !href.includes('Inter')) {
      return;
    }
    userLinks.push(linkEl.outerHTML);
  });

  // 4. Reconstruct a standalone HTML document
  const headContent = [...userLinks, ...userStyles].join('\n');

  if (headContent.trim()) {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
${headContent}
</head>
<body>
${userBodyHTML}
</body>
</html>`;
  }

  // If no styles/links, return just the body content (simpler source)
  return userBodyHTML;
}

/**
 * Get clean HTML from the editor iframe for export.
 * Uses draftHTML if available, falls back to originalHTML.
 */
export function getExportHTML(store) {
  const html = store.draftHTML || store.originalHTML;
  return html;
}

/**
 * Build a <script> block that measures the natural content height of .ws-page
 * and applies CSS zoom to scale it down if content overflows Letter height.
 * This replicates the PDF export's scale-to-fit logic in the editor iframe,
 * ensuring WYSIWYG parity between the editor preview and PDF output.
 *
 * Posts a { type:'PAGE_SCALED', height, scaleFactor } message to parent
 * so the Canvas component can resize the iframe container accordingly.
 */
export function buildScaleToFitScript() {
  return `
<script id="ws-scale-to-fit">
(function(){
  var LETTER_H = 1054; // 279mm at 96dpi

  function scaleToFit(){
    var page = document.querySelector('.ws-page') || document.querySelector('.page');
    if(!page) return;

    // Remove any previous scale styling
    var prev = document.getElementById('ws-scale-css');
    if(prev) prev.remove();
    page.style.removeProperty('zoom');

    // Temporarily expand so we can measure natural height
    var origH = page.style.height;
    var origMaxH = page.style.maxHeight;
    var origOverflow = page.style.overflow;
    page.style.setProperty('height','auto','important');
    page.style.setProperty('max-height','none','important');
    page.style.setProperty('overflow','visible','important');

    var wsBody = page.querySelector('.ws-body') || page.querySelector('.body');
    var origBodyOverflow;
    if(wsBody){
      origBodyOverflow = wsBody.style.overflow;
      wsBody.style.setProperty('overflow','visible','important');
    }

    // Force layout recalc
    void page.offsetHeight;

    var naturalH = page.scrollHeight;

    // Restore original styles
    if(origH) page.style.height = origH; else page.style.removeProperty('height');
    if(origMaxH) page.style.maxHeight = origMaxH; else page.style.removeProperty('max-height');
    if(origOverflow) page.style.overflow = origOverflow; else page.style.removeProperty('overflow');
    if(wsBody){
      if(origBodyOverflow) wsBody.style.overflow = origBodyOverflow;
      else wsBody.style.removeProperty('overflow');
    }

    // Calculate scale factor
    var scale = 1;
    if(naturalH > LETTER_H){
      scale = Math.max(LETTER_H / naturalH, 0.5);
    }

    // Apply zoom-based scaling if needed
    if(scale < 1){
      var s = document.createElement('style');
      s.id = 'ws-scale-css';
      s.innerHTML = 
        '.ws-page, .page {' +
        '  zoom: ' + scale + ' !important;' +
        '  width: 100% !important;' +
        '  min-height: ' + (LETTER_H / scale) + 'px !important;' +
        '  overflow: visible !important;' +
        '}' +
        '.ws-body, .body {' +
        '  overflow: visible !important;' +
        '}';
      document.head.appendChild(s);
    }

    // Notify parent of the final scaled page height
    // After zoom, the visual height is naturalH * scale (capped at LETTER_H)
    var finalH = scale < 1 ? LETTER_H : naturalH;
    window.parent.postMessage({
      type: 'PAGE_SCALED',
      height: finalH,
      naturalHeight: naturalH,
      scaleFactor: scale
    }, '*');
  }

  // Run after fonts load and DOM settles
  if(document.fonts && document.fonts.ready){
    document.fonts.ready.then(function(){
      setTimeout(scaleToFit, 150);
    });
  } else {
    setTimeout(scaleToFit, 400);
  }

  // Re-run when content changes (editor edits trigger HTML_UPDATED)
  var observer = new MutationObserver(function(){
    clearTimeout(observer._timer);
    observer._timer = setTimeout(scaleToFit, 300);
  });
  observer.observe(document.body, { childList:true, subtree:true, characterData:true, attributes:true });
})();
` + `</${'script'}>`;
}

export { TEMPLATE_CSS, TEMPLATE_HEADER, TEMPLATE_FOOTER };
