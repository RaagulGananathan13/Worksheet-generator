import { memo, useMemo, useCallback, forwardRef } from 'react';

/**
 * Renders a block's original HTML inside a lightweight iframe.
 * 
 * ALL content inside the iframe is contenteditable — the user can
 * click any text/element and edit it directly, just like in a
 * word processor. Changes are captured via onContentChange callback.
 */
const HTMLPreviewBlock = memo(forwardRef(function HTMLPreviewBlock(
  { block, isSelected, onContentHeight, onContentChange },
  ref
) {
  const { outerHTML, styleSheet, fontLinks } = block.content;

  const srcdoc = useMemo(() => {
    if (!outerHTML) return '';

    const fontLinksHTML = (fontLinks || [])
      .map(href => `<link rel="stylesheet" href="${href}">`)
      .join('\n');

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
${fontLinksHTML}
<style>${styleSheet || ''}</style>
<style>
/* Override body-level styles for per-block rendering */
html, body {
  margin: 0 !important;
  padding: 0 !important;
  background: white !important;
  overflow: visible !important;
  width: 100% !important;
  min-height: 100% !important;
}
/* Editable highlights */
[contenteditable]:focus {
  outline: 2px solid rgba(59, 130, 246, 0.5) !important;
  outline-offset: 2px !important;
  border-radius: 2px !important;
}
/* Hover hint for editable elements */
body > * * {
  transition: background-color 0.15s ease;
}
body.editing-mode > * *:hover {
  background-color: rgba(59, 130, 246, 0.06) !important;
  cursor: text !important;
}
</style>
<script>
// Make all text-containing elements editable on click
document.addEventListener('DOMContentLoaded', function() {
  document.body.classList.add('editing-mode');
  
  // Make all leaf text elements contenteditable
  function makeEditable(el) {
    if (el.children.length === 0 && el.textContent.trim().length > 0) {
      el.contentEditable = 'true';
    }
    // Also make elements with direct text nodes editable
    for (var node of el.childNodes) {
      if (node.nodeType === 3 && node.textContent.trim().length > 0) {
        el.contentEditable = 'true';
        break;
      }
    }
    for (var child of el.children) {
      makeEditable(child);
    }
  }
  makeEditable(document.body);
  
  // Report content changes back to parent
  document.body.addEventListener('input', function() {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({
        type: 'BLOCK_CONTENT_CHANGE',
        blockId: '${block.id}',
        html: document.body.innerHTML
      }, '*');
    }
  });
  
  // Report height after load
  setTimeout(function() {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({
        type: 'BLOCK_HEIGHT',
        blockId: '${block.id}',
        height: document.body.scrollHeight
      }, '*');
    }
  }, 150);
});
</script>
</head>
<body>${outerHTML}</body>
</html>`;
  }, [outerHTML, styleSheet, fontLinks, block.id]);

  if (!outerHTML) {
    return (
      <div className="w-full h-full flex items-center justify-center border border-dashed border-gray-300/30 rounded">
        <span className="text-[10px] text-gray-400/50 italic select-none">Empty block</span>
      </div>
    );
  }

  return (
    <iframe
      ref={ref}
      srcDoc={srcdoc}
      title="Block preview"
      className="w-full border-none"
      sandbox="allow-same-origin allow-scripts"
      style={{
        display: 'block',
        background: 'white',
        height: '100%',
        minHeight: '100%',
        // Only allow interaction when selected
        pointerEvents: isSelected ? 'auto' : 'none',
      }}
    />
  );
}));

export default HTMLPreviewBlock;
