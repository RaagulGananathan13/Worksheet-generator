/**
 * Sinhala Template Wrapper Engine
 * Wraps user-uploaded worksheet HTML content inside the
 * GeniusBees Sinhala template (header + body + footer).
 *
 * This is the Sinhala counterpart of templateWrapper.js.
 * Uses 'Noto Sans Sinhala' for proper Sinhala Unicode rendering.
 */

const SINHALA_TEMPLATE_CSS = `
  *,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
  @page{size:216mm 279mm;margin:0}
  html{height:100%}
  body{
    font-family:'Noto Sans Sinhala','Iskoola Pota','Poppins',Arial,sans-serif;
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
    .ws-page{margin:0;width:216mm;min-height:279mm;display:flex!important;flex-direction:column!important;overflow:hidden}
    .ws-header{break-inside:avoid;page-break-inside:avoid;flex-shrink:0!important}
    .ws-body{flex:1 1 auto!important;min-height:0!important;overflow:hidden!important}
    .ws-footer{break-inside:avoid;page-break-inside:avoid;flex-shrink:0!important;margin-top:auto!important}
    .ws-footer-copyright{display:none!important}
    .ws-footer-info{display:flex!important;width:100%!important;justify-content:space-between!important}
    .ws-body-content>*{break-inside:auto}
  }

  /* ═══ HEADER ═══ */
  .ws-header, .ws-header * { font-family: 'Poppins', Arial, sans-serif !important; }
  .ws-header { padding: 7mm 12mm 5mm 12mm; border-bottom: none; display: flex; gap: 15px; flex-shrink: 0; }
  .ws-header-left { width: 120px; flex-shrink: 0; display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
  .ws-header-left img { width: 140px; height: auto; display: block; margin-left: -10px; }
  .ws-grade-table { border-collapse: collapse; margin-left: 4px; font-family: 'Poppins', Arial, sans-serif !important; }
  .ws-grade-table td { width: 40px; height: 35px; text-align: center; font-size: 18px; font-weight: 400; color: #555; border: none; font-family: 'Poppins', Arial, sans-serif !important; }
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
  .ws-footer, .ws-footer *, .ws-vertical-copyright { font-family: 'Times New Roman', Times, serif !important; }
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
  .ws-eng-text { font-family: 'Times New Roman', Times, serif !important; }
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

const SINHALA_TEMPLATE_HEADER = `
  <div class="ws-header">
    <div class="ws-header-left">
      <img src="logo.jpg" alt="GeniusBees">
      <table class="ws-grade-table">
        <tr><td>A+</td><td>B+</td><td>C</td></tr>
        <tr><td>A</td><td>B</td><td>D</td></tr>
      </table>
    </div>
    <div class="ws-header-mid">
      <div class="ws-activity-id">අභ්&zwj;යාස පත්&zwj;රිකා අංකය : 140100100001</div>
      <div class="ws-activity-title">ඉලක්කම් දෙකේ සංඛ්&zwj;යා එකතු කිරීම</div>
      <div class="ws-form-fields">
        <div class="ws-form-row">
          <span class="ws-f-label">අංකය</span>
          <div class="ws-f-line-dashed"></div>
        </div>
        <div class="ws-form-row">
          <span class="ws-f-label">නම </span>
          <div class="ws-f-line-dashed"></div>
        </div>
        <div class="ws-form-row">
          <span class="ws-f-label">දිනය</span>
          <div class="ws-d-line-dashed"></div><span class="ws-d-sep">/</span><div class="ws-d-line-dashed"></div><span class="ws-d-sep">/</span><div class="ws-d-line-y-dashed"></div>
          <span class="ws-f-label" style="margin-left:4px">ආරම්භක වේලාව</span>
          <div class="ws-f-line-dashed"></div>
          <span class="ws-f-label" style="margin-left:4px">අවසන් වේලාව</span>
          <div class="ws-f-line-dashed"></div>
        </div>
      </div>
    </div>
    <div class="ws-header-right"></div>
  </div>`;

const SINHALA_TEMPLATE_FOOTER = `
  <div class="ws-vertical-copyright">ප්&zwj;රකාශන හිමිකම© 2026 GeniusBees Inc. සියලුම හිමිකම් ඇවිරිණි.</div>
  <div class="ws-footer">
    <div class="ws-footer-info">
      <span class="ws-eng-text">www.geniusbees.com</span>
      <span class="ws-eng-text">info@geniusbees.com</span>
      <span>මෙම අභ්&zwj;යාස පත්&zwj;රිකාව geniusbees.com හි ලියාපදිංචි සිසුන් සඳහා පමණි.</span>
    </div>
  </div>`;

/**
 * Extract just the <body> inner content from full HTML.
 */
function extractBodyContent(html) {
  const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  if (bodyMatch) return bodyMatch[1].trim();
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
  const styleRegex = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  let match;
  while ((match = styleRegex.exec(html)) !== null) {
    styles.push(match[0]);
  }
  const linkRegex = /<link[^>]*rel=["']stylesheet["'][^>]*\/?>/gi;
  while ((match = linkRegex.exec(html)) !== null) {
    styles.push(match[0]);
  }
  return styles.join('\n');
}

/**
 * Wrap user HTML content inside the GeniusBees Sinhala template.
 * Preserves original CSS while adding Sinhala template structure.
 */
export function wrapInSinhalaTemplate(userHTML) {
  const bodyContent = extractBodyContent(userHTML);
  const originalStyles = extractHeadStyles(userHTML);

  return `<!DOCTYPE html>
<html lang="si">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GeniusBees වැඩ පත්‍රිකාව</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Sinhala:wght@300;400;500;600;700&family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>${SINHALA_TEMPLATE_CSS}</style>
${originalStyles}
</head>
<body>
<div class="ws-page">
${SINHALA_TEMPLATE_HEADER}
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
${SINHALA_TEMPLATE_FOOTER}
</div>
</body>
</html>`;
}

/**
 * Unwrap user HTML content from the GeniusBees Sinhala template.
 * Reverse of wrapInSinhalaTemplate() — extracts user body content
 * and user styles for source code sync.
 */
export function unwrapFromSinhalaTemplate(wrappedHTML) {
  if (!wrappedHTML) return '';

  const parser = new DOMParser();
  const doc = parser.parseFromString(wrappedHTML, 'text/html');

  // 1. Extract user body content from .ws-body-content
  const bodyContentEl = doc.querySelector('.ws-body-content');
  if (!bodyContentEl) {
    return doc.body ? doc.body.innerHTML.trim() : wrappedHTML;
  }
  const userBodyHTML = bodyContentEl.innerHTML.trim();

  // 2. Extract user styles (exclude template CSS and editor injections)
  const userStyles = [];
  doc.querySelectorAll('style').forEach((styleEl) => {
    const id = styleEl.id || '';
    if (id === 'ws-editor-styles' || id === 'ws-readonly-styles' ||
        id === 'ws-scale-to-fit' || id === 'ws-scale-css' ||
        id === 'ws-pdf-base' || id === 'ws-pdf-scale') {
      return;
    }
    const content = styleEl.textContent || '';
    // Skip the main template CSS
    if (content.includes('.ws-page') && content.includes('.ws-header') &&
        content.includes('.ws-footer') && content.includes('@page')) {
      return;
    }
    userStyles.push(`<style>${content}</style>`);
  });

  // 3. Extract user stylesheet links (exclude Sinhala template fonts)
  const userLinks = [];
  doc.querySelectorAll('link[rel="stylesheet"]').forEach((linkEl) => {
    const href = linkEl.getAttribute('href') || '';
    if (href.includes('fonts.googleapis.com') && href.includes('Noto+Sans+Sinhala')) {
      return;
    }
    userLinks.push(linkEl.outerHTML);
  });

  // 4. Reconstruct
  const headContent = [...userLinks, ...userStyles].join('\n');

  if (headContent.trim()) {
    return `<!DOCTYPE html>
<html lang="si">
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

  return userBodyHTML;
}

export { SINHALA_TEMPLATE_CSS, SINHALA_TEMPLATE_HEADER, SINHALA_TEMPLATE_FOOTER };
