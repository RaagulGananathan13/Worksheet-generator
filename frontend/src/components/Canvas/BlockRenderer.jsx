import { memo, useState, useCallback, useRef, useEffect } from 'react';
import HTMLPreviewBlock from '../Blocks/HTMLPreviewBlock';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Renders a single block on the canvas.
 *
 * - Auto-height: Listens for postMessage from iframe to adjust height
 * - Inline editing: When selected, iframe becomes interactive and
 *   all text elements are contenteditable
 * - Content sync: Captures edits from iframe via postMessage
 */
const BlockRenderer = memo(function BlockRenderer({ block, isSelected, onSelect }) {
  const iframeRef = useRef(null);
  const heightFixed = useRef(false);
  const updateBlockSize = useWorksheetStore((s) => s.updateBlockSize);
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);

  // Listen for postMessage from block iframes
  useEffect(() => {
    function handleMessage(e) {
      if (!e.data || typeof e.data !== 'object') return;
      
      if (e.data.type === 'BLOCK_HEIGHT' && e.data.blockId === block.id) {
        if (!heightFixed.current && e.data.height > block.size.height + 5) {
          heightFixed.current = true;
          updateBlockSize(block.id, block.size.width, e.data.height + 4);
        }
      }
      
      if (e.data.type === 'BLOCK_CONTENT_CHANGE' && e.data.blockId === block.id) {
        updateBlockContent(block.id, { outerHTML: e.data.html });
      }
    }

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [block.id, block.size.width, block.size.height, updateBlockSize, updateBlockContent]);

  return (
    <div
      className={`worksheet-block absolute group ${
        isSelected
          ? 'ring-2 ring-blue-500 ring-offset-0 shadow-lg shadow-blue-500/20 z-10'
          : 'hover:ring-1 hover:ring-blue-400/30'
      } ${block.meta?.locked ? 'opacity-80 cursor-not-allowed' : ''}`}
      data-block-id={block.id}
      style={{
        left: block.position.x,
        top: block.position.y,
        width: block.size.width,
        height: block.size.height,
        overflow: 'hidden',
        borderRadius: '2px',
        cursor: isSelected ? 'default' : 'move',
      }}
      onMouseDown={isSelected ? undefined : onSelect}
      onClick={!isSelected ? onSelect : undefined}
    >
      <HTMLPreviewBlock
        ref={iframeRef}
        block={block}
        isSelected={isSelected}
      />

      {/* Selected indicator — edit hint */}
      {isSelected && (
        <div className="absolute bottom-0 left-0 right-0 h-5 bg-blue-500/80 flex items-center justify-center pointer-events-none z-20">
          <span className="text-[9px] text-white font-medium tracking-wide">Click any text to edit</span>
        </div>
      )}

      {/* Type badge on hover */}
      {!isSelected && (
        <div className="absolute -top-5 left-0 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          <span className="text-[9px] bg-surface-800/90 text-surface-300 px-1.5 py-0.5 rounded shadow">
            {block.type.replace('Block', '')}
          </span>
        </div>
      )}
    </div>
  );
});

export default BlockRenderer;
