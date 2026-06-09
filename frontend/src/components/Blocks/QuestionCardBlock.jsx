import { memo, useCallback } from 'react';
import useWorksheetStore from '../../store/worksheetStore';
import OptionBadge from './OptionBadge';

/**
 * Renders a question card: image + word with blank + option badges.
 * Supports inline editing of the word text via contentEditable.
 */
const QuestionCardBlock = memo(function QuestionCardBlock({ block }) {
  const { image, word, options } = block.content;
  const styles = block.styles;
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);

  const handleWordBlur = useCallback((e) => {
    updateBlockContent(block.id, { word: e.target.textContent });
  }, [block.id, updateBlockContent]);

  return (
    <div
      className="w-full h-full flex flex-col items-center justify-center p-2"
      style={{ fontFamily: styles.fontFamily }}
    >
      {image && (
        <img
          src={image.src}
          alt={image.alt}
          className="object-contain mb-1 pointer-events-none"
          style={{
            width: styles.imageSize?.width || 110,
            height: styles.imageSize?.height || 110,
          }}
          draggable={false}
        />
      )}

      <div
        contentEditable
        suppressContentEditableWarning
        onBlur={handleWordBlur}
        className="outline-none cursor-text mb-2 text-center leading-none"
        style={{
          fontSize: styles.fontSize || 24,
          fontWeight: styles.fontWeight || '400',
          color: styles.color || '#000',
        }}
      >
        {word}
      </div>

      {options && options.length > 0 && (
        <div className="flex gap-3 justify-center">
          {options.map((opt) => (
            <OptionBadge
              key={opt.id}
              option={opt}
              blockId={block.id}
              bgColor={styles.optionBg}
              radius={styles.optionRadius}
              fontSize={styles.fontSize}
            />
          ))}
        </div>
      )}
    </div>
  );
});

export default QuestionCardBlock;
