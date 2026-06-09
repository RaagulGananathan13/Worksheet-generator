import { memo, useCallback } from 'react';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Generic block renderer — used for worksheet items that don't match
 * a specific pattern (equation, questionCard, etc).
 *
 * Renders the preserved inline-styled HTML faithfully,
 * with a text editing fallback.
 */
const GenericBlock = memo(function GenericBlock({ block }) {
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);

  const handleTextBlur = useCallback((e) => {
    updateBlockContent(block.id, { text: e.target.textContent.trim() });
  }, [block.id, updateBlockContent]);

  // If we have innerHTML, render it faithfully
  if (block.content?.innerHTML) {
    return (
      <div
        className="w-full h-full overflow-hidden"
        style={{
          fontFamily: block.styles.fontFamily || "'Poppins', sans-serif",
          fontSize: block.styles.fontSize || 16,
          color: block.styles.color || '#000',
        }}
        dangerouslySetInnerHTML={{ __html: block.content.innerHTML }}
      />
    );
  }

  // Fallback: editable text
  if (block.content?.text) {
    return (
      <div
        contentEditable
        suppressContentEditableWarning
        onBlur={handleTextBlur}
        className="w-full h-full overflow-hidden outline-none cursor-text"
        style={{
          fontFamily: block.styles.fontFamily || "'Poppins', sans-serif",
          fontSize: block.styles.fontSize || 16,
          color: block.styles.color || '#000',
        }}
      >
        {block.content.text}
      </div>
    );
  }

  // Empty block
  return (
    <div className="w-full h-full flex items-center justify-center border border-dashed border-gray-300/30 rounded">
      <span className="text-[10px] text-gray-400/50 italic select-none">Empty block</span>
    </div>
  );
});

export default GenericBlock;
