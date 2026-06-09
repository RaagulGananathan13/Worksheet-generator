import { memo, useCallback } from 'react';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Renders an editable text block using contentEditable.
 * Syncs to store on blur to avoid cursor jumping.
 */
const TextBlock = memo(function TextBlock({ block }) {
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);

  const handleBlur = useCallback((e) => {
    updateBlockContent(block.id, { text: e.target.textContent });
  }, [block.id, updateBlockContent]);

  return (
    <div
      contentEditable
      suppressContentEditableWarning
      onBlur={handleBlur}
      className="w-full h-full flex items-center outline-none cursor-text"
      style={{
        fontSize: block.styles.fontSize || 16,
        fontWeight: block.styles.fontWeight || '400',
        fontFamily: block.styles.fontFamily || 'Inter, sans-serif',
        color: block.styles.color || '#000',
        backgroundColor: block.styles.backgroundColor || 'transparent',
        textAlign: block.styles.textAlign || 'left',
      }}
    >
      {block.content.text}
    </div>
  );
});

export default TextBlock;
