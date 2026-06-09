import { memo, useCallback } from 'react';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Renders a single option badge/chip (e.g. a letter choice like "d" or "p").
 * Label is inline-editable via contentEditable.
 */
const OptionBadge = memo(function OptionBadge({ option, blockId, bgColor, radius, fontSize }) {
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);
  const blocks = useWorksheetStore((s) => s.blocks);

  const handleBlur = useCallback((e) => {
    const block = blocks.find((b) => b.id === blockId);
    if (!block) return;
    const updatedOptions = block.content.options.map((opt) =>
      opt.id === option.id ? { ...opt, label: e.target.textContent.trim() } : opt
    );
    updateBlockContent(blockId, { options: updatedOptions });
  }, [blockId, option.id, blocks, updateBlockContent]);

  return (
    <div
      className="flex items-center justify-center cursor-text select-none"
      style={{
        width: 52,
        height: 44,
        background: bgColor || '#edbb95',
        borderRadius: radius || 5,
        fontSize: fontSize || 24,
        fontWeight: 400,
        color: '#000',
      }}
    >
      <span
        contentEditable
        suppressContentEditableWarning
        onBlur={handleBlur}
        className="outline-none"
      >
        {option.label}
      </span>
    </div>
  );
});

export default OptionBadge;
