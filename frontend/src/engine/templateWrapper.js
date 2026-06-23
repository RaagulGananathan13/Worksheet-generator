/**
 * Template Wrapper Engine
 * Wraps user-uploaded worksheet HTML content inside the
 * GeniusBees template (header + body + footer).
 */

const TEMPLATE_CSS = `
  *,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
  @page{size:A4;margin:0}
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
    .ws-page{margin:0;width:210mm;min-height:0;height:auto;display:block;overflow:visible}
    .ws-header{break-inside:avoid;page-break-inside:avoid}
    .ws-body{flex:none}
    .ws-footer{break-inside:avoid;page-break-inside:avoid;position:relative;margin-top:0}
    .ws-footer-copyright{display:block!important;width:100%!important;text-align:center!important}
    .ws-footer-info{display:flex!important;width:100%!important;justify-content:center!important}
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
    padding:3mm 12mm 4mm 12mm;
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
    justify-content: center !important;
    gap: 50px !important;
    flex-wrap: wrap !important;
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
      <div class="ws-activity-id">Activity ID : 140100100001</div>
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
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
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
 * Get clean HTML from the editor iframe for export.
 * Uses draftHTML if available, falls back to originalHTML.
 */
export function getExportHTML(store) {
  const html = store.draftHTML || store.originalHTML;
  return html;
}

export { TEMPLATE_CSS, TEMPLATE_HEADER, TEMPLATE_FOOTER };
