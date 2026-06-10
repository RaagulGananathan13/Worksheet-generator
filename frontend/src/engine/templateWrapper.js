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
    .ws-footer-row{display:flex!important;width:100%!important}
    .ws-footer-row span{display:inline-block!important}
    .ws-body-content>*{break-inside:auto}
  }

  /* ═══ HEADER ═══ */
  .ws-header { padding: 7mm 12mm 5mm 8mm; border-bottom: none; display: flex; gap: 15px; flex-shrink: 0; }
  .ws-header-left { width: 120px; flex-shrink: 0; display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
  .ws-header-left img { width: 140px; height: auto; display: block; margin-left: -10px; }
  .ws-grade-table { border-collapse: collapse; margin-left: 4px; }
  .ws-grade-table td { width: 40px; height: 35px; text-align: center; font-size: 18px; font-weight: 300; color: #555; border: none; }
  .ws-grade-table tr:first-child td { border-bottom: 1px solid #777; }
  .ws-grade-table td:not(:last-child) { border-right: 1px solid #777; }
  .ws-header-mid { flex: 1; padding: 0 5px; display: flex; flex-direction: column; overflow: hidden; }
  .ws-activity-id { font-size: 15px; font-weight: 700; color: #111; margin-bottom: 4px; }
  .ws-activity-title { font-size: 14px; font-weight: 700; color: #111; margin-bottom: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ws-form-fields { display: flex; flex-direction: column; gap: 8px; }
  .ws-form-row { display: flex; align-items: baseline; gap: 6px; font-size: 12px; color: #333; }
  .ws-f-label { font-weight: 400; white-space: nowrap; color: #333; }
  .ws-f-line-dashed { flex: 1; border-bottom: 1px dashed #777; min-width: 20px; margin-bottom: 3px; }
  .ws-f-line-sm-dashed { width: 75px; border-bottom: 1px dashed #777; margin-bottom: 3px; }
  .ws-d-line-dashed { width: 22px; border-bottom: 1px dashed #777; margin-bottom: 3px; }
  .ws-d-line-y-dashed { width: 38px; border-bottom: 1px dashed #777; margin-bottom: 3px; }
  .ws-d-sep { font-weight: 400; margin: 0 1px; color: #666; }
  .ws-header-right { width: 115px; flex-shrink: 0; display: flex; align-items: flex-start; justify-content: flex-end; }
  .ws-header-right img { width: 115px; height: 115px; display: block; }

  /* ═══ BODY ═══ */
  .ws-body{
    flex:1;
    position:relative;
    padding:3mm 8mm 4mm 8mm;
  }
  .ws-wm-wrap{position:absolute;inset:0;overflow:hidden;pointer-events:none;z-index:0}
  .ws-wm{
    position:absolute;font-family:'Poppins',sans-serif;
    font-size:130px;font-weight:700;font-style:italic;
    color:rgba(0,0,0,.035);user-select:none;letter-spacing:-3px;
    line-height:1;transform:rotate(-15deg);
  }
  .ws-wm1{top:8%;right:10%}
  .ws-wm2{top:42%;left:5%}
  .ws-wm3{bottom:8%;right:18%}
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
  .ws-footer {
    padding: 3mm 15mm 6mm 15mm;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: 'Times New Roman', Times, serif;
    color: #111;
    flex-shrink: 0;
    margin-top: auto;
  }
  .ws-footer-left {
    flex: 1;
    text-align: left;
    font-size: 10px;
    font-weight: 500;
  }
  .ws-footer-center {
    flex: 2;
    text-align: center;
    font-size: 9px;
    font-weight: 500;
  }
  .ws-footer-right {
    flex: 1;
    text-align: right;
    font-size: 10px;
    font-weight: bold;
  }
  .ws-vertical-copyright {
    position: absolute;
    left: -193px;
    width: 400px;
    top: 50%;
    text-align: center;
    transform: translateY(-50%) rotate(90deg);
    font-family: 'Times New Roman', Times, serif;
    font-size: 10px;
    font-weight: 500;
    color: #111;
    pointer-events: njpg;
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
          <div class="ws-d-line-dashed"></div>
          <span class="ws-d-sep">/</span>
          <div class="ws-d-line-dashed"></div>
          <span class="ws-d-sep">/</span>
          <div class="ws-d-line-y-dashed"></div>
          <span class="ws-f-label" style="margin-left:8px">Start time</span>
          <div class="ws-f-line-sm-dashed"></div>
          <span class="ws-f-label" style="margin-left:8px">Finish time</span>
          <div class="ws-f-line-sm-dashed"></div>
        </div>
      </div>
    </div>
    <div class="ws-header-right">
      <img src="image.png" alt="QR Code">
    </div>
  </div>`;

const TEMPLATE_FOOTER = `
  <div class="ws-vertical-copyright">Copyright&copy; 2026 GeniusBees Inc. All rights reserved.</div>
  <div class="ws-footer">
    <span class="ws-footer-left">www.geniusbees.com</span>
    <span class="ws-footer-center">This worksheet is for the use of registered Geniusbees.com students only.</span>
    <span class="ws-footer-right">Page :1</span>
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
      <div class="ws-wm ws-wm1">GB</div>
      <div class="ws-wm ws-wm2">GB</div>
      <div class="ws-wm ws-wm3">GB</div>
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
