import { rgbToHex, parsePixelValue } from '../utils/helpers';

/**
 * HTML Parser v4 — Render in hidden iframe, walk DOM, extract:
 *   1. Element hierarchy with parentIndex/childIndices
 *   2. outerHTML for each element
 *   3. Worksheet-level styleSheet + fontLinks
 *   4. Root element offset (critical for overlay alignment)
 */
export async function parseHTMLString(htmlString) {
  const iframe = await renderInHiddenIframe(htmlString);

  try {
    const worksheetMeta = extractWorksheetMeta(iframe);
    const elements = extractElements(iframe);
    return { elements, worksheetMeta };
  } finally {
    document.body.removeChild(iframe);
  }
}

/** Parser iframe width — must be constant so editor iframe matches */
const IFRAME_WIDTH = 1100;

function renderInHiddenIframe(htmlString) {
  return new Promise((resolve, reject) => {
    const iframe = document.createElement('iframe');
    iframe.style.cssText =
      `visibility:hidden;position:absolute;top:-9999px;left:-9999px;width:${IFRAME_WIDTH}px;height:6000px;border:none;`;
    iframe.srcdoc = htmlString;
    document.body.appendChild(iframe);

    iframe.addEventListener('load', () => resolve(iframe));
    iframe.addEventListener('error', () => {
      document.body.removeChild(iframe);
      reject(new Error('Failed to load HTML in iframe'));
    });

    setTimeout(() => { if (iframe.parentNode) resolve(iframe); }, 5000);
  });
}

function findWorksheetRoot(doc) {
  return doc.querySelector('.worksheet') ||
         doc.querySelector('.ws-questions') ||
         doc.querySelector('.worksheet-container') ||
         doc.querySelector('[class*="worksheet"]') ||
         doc.querySelector('[class*="questions"]') ||
         doc.body;
}

function extractWorksheetMeta(iframe) {
  const doc = iframe.contentDocument;
  const root = findWorksheetRoot(doc);
  const rootRect = root.getBoundingClientRect();
  const bodyRect = doc.body.getBoundingClientRect();
  const title = doc.querySelector('title')?.textContent || 'Untitled Worksheet';

  // Extract all <style> tag contents
  let styleSheet = '';
  doc.querySelectorAll('style').forEach(tag => { styleSheet += tag.textContent + '\n'; });

  // Extract font links (Google Fonts, etc.)
  const fontLinks = [];
  doc.querySelectorAll('link[rel="stylesheet"]').forEach(link => {
    if (link.href) fontLinks.push(link.href);
  });

  return {
    title,
    // Use full iframe width so editor iframe renders identically
    width: IFRAME_WIDTH,
    height: Math.max(Math.round(bodyRect.height), Math.round(rootRect.top + rootRect.height + 50), 800),
    styleSheet,
    fontLinks,
    // Root offset within the iframe — critical for overlay alignment
    rootOffset: {
      x: Math.round(rootRect.left),
      y: Math.round(rootRect.top),
    },
  };
}

function extractElements(iframe) {
  const doc = iframe.contentDocument;
  const win = iframe.contentWindow;
  const root = findWorksheetRoot(doc);
  const rootRect = root.getBoundingClientRect();

  const elements = [];
  const domToIndex = new Map();

  function walkDOM(el, depth = 0, parentDomElement = null) {
    if (!el || !el.tagName) return;
    const tag = el.tagName.toLowerCase();
    if (['script', 'style', 'link', 'meta', 'head', 'noscript', 'br'].includes(tag)) return;

    const rect = el.getBoundingClientRect();
    const styles = win.getComputedStyle(el);
    if (rect.width === 0 && rect.height === 0 && styles.display === 'none') return;

    const index = elements.length;
    const parentIndex = parentDomElement ? (domToIndex.get(parentDomElement) ?? -1) : -1;

    const element = {
      index,
      tag,
      id: el.id || null,
      classes: [...el.classList],
      text: getDirectText(el),
      fullText: (el.textContent || '').trim(),
      outerHTML: el.outerHTML,
      childCount: el.children.length,
      depth,
      parentIndex,
      childIndices: [],
      rect: {
        x: Math.round(rect.left - rootRect.left),
        y: Math.round(rect.top - rootRect.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      computedStyles: {
        display: styles.display,
        position: styles.position,
        fontSize: parsePixelValue(styles.fontSize),
        fontWeight: styles.fontWeight,
        fontFamily: styles.fontFamily,
        color: rgbToHex(styles.color),
        backgroundColor: rgbToHex(styles.backgroundColor),
        textAlign: styles.textAlign,
        gridTemplateColumns: styles.gridTemplateColumns,
        flexDirection: styles.flexDirection,
      },
      imgSrc: tag === 'img' ? el.src : null,
      imgAlt: tag === 'img' ? (el.alt || '') : null,
      isEmptyVisual: (el.textContent || '').trim() === '' && tag !== 'img' && rect.width > 0 && rect.height > 0,
    };

    domToIndex.set(el, index);
    elements.push(element);

    if (parentIndex >= 0 && elements[parentIndex]) {
      elements[parentIndex].childIndices.push(index);
    }

    for (const child of el.children) {
      walkDOM(child, depth + 1, el);
    }
  }

  walkDOM(root);
  return elements;
}

function getDirectText(el) {
  let text = '';
  for (const node of el.childNodes) {
    if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
  }
  return text.trim();
}
