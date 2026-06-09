import { BLOCK_TYPES } from '../utils/constants';
import { generateId } from '../utils/helpers';

/**
 * Detection Engine v4 — Universal Worksheet Support
 *
 * KEY INSIGHT: Instead of decomposing HTML into atomic React components
 * (which loses CSS layout), each block stores its outerHTML + the worksheet
 * stylesheet. Blocks render via iframe for PERFECT visual fidelity.
 *
 * Pipeline:
 *   1. Detect titles (h1-h6)
 *   2. Detect repeating groups in layout containers
 *   3. Detect repeating groups in block-level containers with same-class children
 *   4. Detect standalone images
 *   5. Remaining meaningful text elements
 *
 * @param {Array} elements - Flat array from htmlParser
 * @param {Object} worksheetMeta - Contains styleSheet, fontLinks
 */
export function detectBlocks(elements, worksheetMeta = {}) {
  const blocks = [];
  const processed = new Set();
  const { styleSheet = '', fontLinks = [] } = worksheetMeta;

  // ── PASS 1: TITLES ──
  for (const el of elements) {
    if (processed.has(el.index)) continue;
    if (isTitle(el)) {
      blocks.push(makeBlock(el, BLOCK_TYPES.TITLE_BLOCK, styleSheet, fontLinks, {
        text: el.fullText,
        level: ({ h1: 1, h2: 2, h3: 3, h4: 4, h5: 5, h6: 6 })[el.tag] || 2,
      }));
      markSubtree(el, elements, processed);
      // Also mark title's wrapper parent if it only wraps the title
      if (el.parentIndex >= 0) {
        const parent = elements[el.parentIndex];
        if (parent && parent.childIndices.length <= 2 && parent.fullText === el.fullText) {
          processed.add(parent.index);
        }
      }
    }
  }

  // ── PASS 2: REPEATING GROUPS IN GRID/FLEX CONTAINERS ──
  for (const el of elements) {
    if (processed.has(el.index)) continue;
    if (!isGridOrFlexContainer(el)) continue;

    const children = getChildren(el, elements).filter(c => !processed.has(c.index));
    if (children.length < 2) continue;

    if (hasRepeatingStructure(children)) {
      children.forEach((child, i) => {
        blocks.push(makeBlock(child, BLOCK_TYPES.GENERIC_BLOCK, styleSheet, fontLinks, {
          text: child.fullText,
          groupIndex: i,
        }));
        markSubtree(child, elements, processed);
      });
      processed.add(el.index);
      continue;
    }
  }

  // ── PASS 3: REPEATING GROUPS IN BLOCK-LEVEL CONTAINERS ──
  // Handles things like .definitions-container, .sentence-section, etc.
  for (const el of elements) {
    if (processed.has(el.index)) continue;
    if (el.childCount < 3) continue;
    if (isGridOrFlexContainer(el)) continue; // Already handled in pass 2

    const children = getChildren(el, elements).filter(c => !processed.has(c.index));
    if (children.length < 3) continue;

    if (hasRepeatingStructure(children)) {
      children.forEach((child, i) => {
        blocks.push(makeBlock(child, BLOCK_TYPES.GENERIC_BLOCK, styleSheet, fontLinks, {
          text: child.fullText,
          groupIndex: i,
        }));
        markSubtree(child, elements, processed);
      });
      processed.add(el.index);
      continue;
    }
  }

  // ── PASS 4: STANDALONE CONTAINERS WITH UNIQUE CONTENT ──
  // Handles word banks, instruction boxes, etc.
  for (const el of elements) {
    if (processed.has(el.index)) continue;
    if (hasProcessedAncestor(el, elements, processed)) { processed.add(el.index); continue; }
    if (el.childCount >= 2 && el.fullText.length > 0 && el.rect.width > 50 && el.rect.height > 20) {
      // Check if this is a meaningful standalone container (word bank, instructions, etc.)
      const unprocessedChildren = getChildren(el, elements).filter(c => !processed.has(c.index));
      if (unprocessedChildren.length >= 2) {
        blocks.push(makeBlock(el, BLOCK_TYPES.GENERIC_BLOCK, styleSheet, fontLinks, {
          text: el.fullText,
        }));
        markSubtree(el, elements, processed);
      }
    }
  }

  // ── PASS 5: STANDALONE IMAGES ──
  for (const el of elements) {
    if (processed.has(el.index)) continue;
    if (hasProcessedAncestor(el, elements, processed)) { processed.add(el.index); continue; }
    if (el.tag === 'img' && el.rect.width > 5 && el.rect.height > 5) {
      blocks.push(makeBlock(el, BLOCK_TYPES.IMAGE_BLOCK, styleSheet, fontLinks, {
        src: el.imgSrc,
        alt: el.imgAlt || '',
      }));
      processed.add(el.index);
    }
  }

  // ── PASS 6: REMAINING TEXT (leaf elements with visible text) ──
  for (const el of elements) {
    if (processed.has(el.index)) continue;
    if (el.depth === 0) { processed.add(el.index); continue; }
    if (hasProcessedAncestor(el, elements, processed)) { processed.add(el.index); continue; }
    // Only create blocks for leaf or near-leaf elements with text
    if (el.childCount > 3) continue;
    if (el.fullText.length > 0 && el.fullText.length < 1000 && el.rect.width > 10) {
      // Don't create text blocks for wrappers — only for elements with direct text
      if (el.childCount > 0 && !el.text) continue;
      blocks.push(makeBlock(el, BLOCK_TYPES.TEXT_BLOCK, styleSheet, fontLinks, {
        text: el.text || el.fullText,
      }));
      markSubtree(el, elements, processed);
    }
  }

  return blocks;
}

// ═══════════════════════════════════════════════════
//  BLOCK FACTORY
// ═══════════════════════════════════════════════════

/**
 * Create a block with original HTML preserved for iframe rendering.
 */
function makeBlock(el, type, styleSheet, fontLinks, extraContent = {}) {
  return {
    id: generateId(),
    type,
    position: { x: el.rect.x, y: el.rect.y },
    size: { width: Math.max(el.rect.width, 40), height: Math.max(el.rect.height, 20) },
    rotation: 0,
    content: {
      ...extraContent,
      outerHTML: el.outerHTML,
      styleSheet,
      fontLinks,
    },
    styles: {
      fontSize: el.computedStyles.fontSize || 16,
      fontWeight: el.computedStyles.fontWeight || '400',
      fontFamily: el.computedStyles.fontFamily || "'Poppins', sans-serif",
      color: el.computedStyles.color || '#000000',
      backgroundColor: el.computedStyles.backgroundColor || 'transparent',
      textAlign: el.computedStyles.textAlign || 'left',
    },
    meta: {
      parentId: null,
      sourceSelector: buildSelector(el),
      order: extraContent.groupIndex || 0,
      locked: false,
      visible: true,
    },
  };
}

// ═══════════════════════════════════════════════════
//  DETECTION RULES
// ═══════════════════════════════════════════════════

function isTitle(el) {
  if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(el.tag)) return true;
  return (
    el.computedStyles.fontSize >= 26 &&
    el.fullText.length > 0 &&
    el.fullText.length < 200 &&
    el.childCount <= 2 &&
    el.rect.y < 200
  );
}

function isGridOrFlexContainer(el) {
  const d = el.computedStyles.display;
  return (
    (d === 'grid' || d === 'flex' || d === 'inline-flex' || d === 'inline-grid') &&
    el.childCount >= 2
  );
}

/**
 * Check if children share the same structure (tag + class pattern)
 * indicating a repeating pattern.
 */
function hasRepeatingStructure(children) {
  if (children.length < 2) return false;

  const first = children[0];
  const firstKey = `${first.tag}|${first.classes.sort().join('.')}`;
  let matchCount = 0;

  for (const child of children) {
    const key = `${child.tag}|${child.classes.sort().join('.')}`;
    if (key === firstKey) matchCount++;
  }

  // At least 60% of children should match the first child's structure
  return matchCount >= children.length * 0.6;
}

// ═══════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════

function getChildren(parent, elements) {
  return parent.childIndices.map(i => elements[i]).filter(Boolean);
}

function markSubtree(el, elements, processed) {
  processed.add(el.index);
  function walk(node) {
    for (const idx of node.childIndices) {
      const child = elements[idx];
      if (child) {
        processed.add(child.index);
        walk(child);
      }
    }
  }
  walk(el);
}

function hasProcessedAncestor(el, elements, processed) {
  let current = el;
  while (current.parentIndex >= 0) {
    if (processed.has(current.parentIndex)) return true;
    current = elements[current.parentIndex];
    if (!current) break;
  }
  return false;
}

function buildSelector(el) {
  if (el.id) return `#${el.id}`;
  let sel = el.tag;
  if (el.classes.length > 0) sel += '.' + el.classes.join('.');
  return sel;
}
