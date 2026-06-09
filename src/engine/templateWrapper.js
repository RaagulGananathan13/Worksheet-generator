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
  .ws-header{
    padding:7mm 12mm 5mm 10mm;
    border-bottom:1.5px solid #222;
    display:flex;
    gap:0;
    flex-shrink:0;
  }
  .ws-header-left{width:150px;flex-shrink:0;display:flex;flex-direction:column;gap:8px}
  .ws-header-left img{width:140px;height:auto;display:block}
  .ws-grade-table{border-collapse:collapse}
  .ws-grade-table td{
    width:40px;height:30px;border:1.5px solid #333;
    text-align:center;font-size:14px;font-weight:500;color:#111;
  }
  .ws-header-mid{flex:1;padding:2px 12px 0 8px;display:flex;flex-direction:column}
  .ws-activity-id{font-size:14.5px;font-weight:600;color:#111;margin-bottom:1px}
  .ws-activity-title{font-size:12.5px;font-weight:400;color:#333;margin-bottom:10px}
  .ws-form-fields{display:flex;flex-direction:column;gap:7px}
  .ws-form-row{display:flex;align-items:baseline;gap:6px;font-size:12px;color:#111}
  .ws-f-label{font-weight:500;white-space:nowrap}
  .ws-f-line{flex:1;border-bottom:1px solid #444;min-width:30px;margin-bottom:2px}
  .ws-f-line-sm{width:75px;border-bottom:1px solid #444;margin-bottom:2px}
  .ws-d-line{width:22px;border-bottom:1px solid #444;margin-bottom:2px}
  .ws-d-line-y{width:38px;border-bottom:1px solid #444;margin-bottom:2px}
  .ws-d-sep{font-weight:500;margin:0 1px}
  .ws-header-right{width:90px;flex-shrink:0;display:flex;align-items:flex-start;justify-content:flex-end}
  .ws-header-right img{width:85px;height:85px;display:block}

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
  .ws-footer{
    padding:2mm 8mm 4mm 8mm;
    border-top:1px solid #222;
    flex-shrink:0;
    margin-top:auto;
  }
  .ws-footer-row{
    display:flex;align-items:center;justify-content:space-between;
    font-size:7px;color:#333;width:100%;gap:4px;
  }
  .ws-footer-row span{display:inline-block;white-space:nowrap}
  .ws-fc{font-weight:400;flex-shrink:0}
  .ws-fs{font-weight:500;color:#111;flex-shrink:0}
  .ws-fn{font-weight:400;flex:1;text-align:center;font-size:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ws-fp{font-weight:700;font-size:10px;color:#111;flex-shrink:0}
`;

const TEMPLATE_HEADER = `
  <div class="ws-header">
    <div class="ws-header-left">
      <img src="gb-logo.jpg" alt="GeniusBees">
      <table class="ws-grade-table">
        <tr><td>A+</td><td>B+</td><td>C+</td></tr>
        <tr><td>A</td><td>B</td><td>C</td></tr>
      </table>
    </div>
    <div class="ws-header-mid">
      <div class="ws-activity-id">Activity ID : 1ABC</div>
      <div class="ws-activity-title">Addition with two digit numbers</div>
      <div class="ws-form-fields">
        <div class="ws-form-row">
          <span class="ws-f-label">ID</span>
          <div class="ws-f-line"></div>
        </div>
        <div class="ws-form-row">
          <span class="ws-f-label">Name</span>
          <div class="ws-f-line"></div>
        </div>
        <div class="ws-form-row">
          <span class="ws-f-label">Data</span>
          <div class="ws-d-line"></div>
          <span class="ws-d-sep">/</span>
          <div class="ws-d-line"></div>
          <span class="ws-d-sep">/</span>
          <div class="ws-d-line-y"></div>
          <span class="ws-f-label" style="margin-left:10px">Start time</span>
          <div class="ws-f-line-sm"></div>
          <span class="ws-f-label" style="margin-left:8px">Finished time</span>
          <div class="ws-f-line-sm"></div>
        </div>
      </div>
    </div>
    <div class="ws-header-right">
      <img src="image.png" alt="QR Code">
    </div>
  </div>`;

const TEMPLATE_FOOTER = `
  <div class="ws-footer">
    <div class="ws-footer-row">
      <span class="ws-fc">Copyright© 2026 GeniusBees. inc. All rights reserved.</span>
      <span class="ws-fs">www.geniusbees.com</span>
      <span class="ws-fn">This worksheet is for the use of registered GeniusBees.Com students only. No other use is permitted.</span>
      <span class="ws-fp">Page :1</span>
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
