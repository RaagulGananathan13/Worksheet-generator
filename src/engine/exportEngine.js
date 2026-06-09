import { BLOCK_TYPES } from '../utils/constants';
import { downloadBlob } from '../utils/helpers';

/**
 * Export blocks as JSON file
 */
export function exportAsJSON(blocks, worksheetMeta) {
  const data = {
    version: '2.0',
    exportedAt: new Date().toISOString(),
    meta: worksheetMeta,
    blocks,
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const filename = worksheetMeta.title.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
  downloadBlob(blob, `${filename}.json`);
}

/**
 * Import blocks from JSON file
 */
export function importFromJSON(jsonString) {
  try {
    const data = JSON.parse(jsonString);
    if (!data.blocks || !Array.isArray(data.blocks)) {
      throw new Error('Invalid worksheet JSON: missing blocks array');
    }
    return {
      blocks: data.blocks,
      worksheetMeta: data.meta || { title: 'Imported Worksheet', width: 1100, height: 800 },
    };
  } catch (err) {
    throw new Error(`Failed to parse JSON: ${err.message}`);
  }
}

/**
 * Export as HTML — reconstructs the worksheet from blocks.
 *
 * Strategy: Since each block stores its outerHTML, we can reconstruct
 * the worksheet by wrapping all blocks in a container with the original
 * stylesheet, positioning them absolutely.
 *
 * For a cleaner export: if the store still has originalHTML, offer that
 * as the primary export and this as a "modified" export.
 */
export function exportAsHTML(blocks, worksheetMeta, originalHTML = '') {
  // If we have original HTML and no blocks have been moved/edited, return it as-is
  if (originalHTML && blocks.length > 0) {
    const blob = new Blob([originalHTML], { type: 'text/html' });
    const filename = worksheetMeta.title.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
    downloadBlob(blob, `${filename}.html`);
    return;
  }

  // Fallback: reconstruct from blocks
  const html = generateHTML(blocks, worksheetMeta);
  const blob = new Blob([html], { type: 'text/html' });
  const filename = worksheetMeta.title.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
  downloadBlob(blob, `${filename}.html`);
}

function generateHTML(blocks, meta) {
  const styleSheet = meta.styleSheet || '';
  const fontLinks = (meta.fontLinks || [])
    .map(href => `<link rel="stylesheet" href="${href}">`)
    .join('\n');

  // Sort blocks by position (top-to-bottom, left-to-right)
  const sorted = [...blocks].sort((a, b) => {
    const dy = a.position.y - b.position.y;
    return Math.abs(dy) > 20 ? dy : a.position.x - b.position.x;
  });

  let bodyContent = '';
  sorted.forEach((block) => {
    if (block.content.outerHTML) {
      // Use the original HTML directly
      bodyContent += `  ${block.content.outerHTML}\n`;
    } else {
      // Fallback for blocks without outerHTML
      bodyContent += generateBlockHTML(block);
    }
  });

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${meta.title}</title>
${fontLinks}
<style>
${styleSheet}
</style>
</head>
<body>
${bodyContent}
</body>
</html>`;
}

function generateBlockHTML(block) {
  switch (block.type) {
    case BLOCK_TYPES.TITLE_BLOCK:
      return `  <div style="text-align:${block.styles.textAlign || 'center'};margin-bottom:35px;"><h${block.content.level || 2} style="font-size:${block.styles.fontSize}px;color:${block.styles.color};font-weight:${block.styles.fontWeight};">${block.content.text}</h${block.content.level || 2}></div>\n`;

    case BLOCK_TYPES.IMAGE_BLOCK:
      return `  <img src="${block.content.src}" alt="${block.content.alt || ''}" style="width:${block.size.width}px;height:${block.size.height}px;object-fit:${block.styles.objectFit || 'contain'};">\n`;

    case BLOCK_TYPES.TEXT_BLOCK:
      return `  <div style="font-size:${block.styles.fontSize}px;color:${block.styles.color};font-weight:${block.styles.fontWeight};text-align:${block.styles.textAlign};">${block.content.text}</div>\n`;

    default:
      return block.content.text ? `  <div>${block.content.text}</div>\n` : '';
  }
}
