import { memo, useCallback } from 'react';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Renders an equation-style question row:
 *   [number prefix]  [equation text]  [answer box]
 * Example: "1.  63 + 39 =  [___]"
 */
const EquationBlock = memo(function EquationBlock({ block }) {
  const { prefix, equation, hasAnswerBox, answerBoxSize } = block.content;
  const styles = block.styles;
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);

  const handlePrefixBlur = useCallback((e) => {
    updateBlockContent(block.id, { prefix: e.target.textContent.trim() });
  }, [block.id, updateBlockContent]);

  const handleEquationBlur = useCallback((e) => {
    updateBlockContent(block.id, { equation: e.target.textContent.trim() });
  }, [block.id, updateBlockContent]);

  return (
    <div
      className="w-full h-full flex items-center gap-3 px-1"
      style={{ fontFamily: styles.fontFamily }}
    >
      {/* Number prefix */}
      <span
        contentEditable
        suppressContentEditableWarning
        onBlur={handlePrefixBlur}
        className="outline-none cursor-text shrink-0"
        style={{
          fontSize: styles.prefixFontSize || 20,
          fontWeight: '400',
          color: styles.prefixColor || '#555',
          minWidth: '30px',
          textAlign: 'left',
        }}
      >
        {prefix}
      </span>

      {/* Equation text */}
      <span
        contentEditable
        suppressContentEditableWarning
        onBlur={handleEquationBlur}
        className="outline-none cursor-text whitespace-nowrap"
        style={{
          fontSize: styles.fontSize || 24,
          fontWeight: styles.fontWeight || '400',
          color: styles.color || '#000',
        }}
      >
        {equation}
      </span>

      {/* Answer box */}
      {hasAnswerBox && (
        <div
          className="shrink-0 ml-auto"
          style={{
            width: answerBoxSize?.width || 85,
            height: answerBoxSize?.height || 48,
            border: `1px solid ${styles.answerBoxBorderColor || '#B3B3B3'}`,
            borderRadius: styles.answerBoxBorderRadius || 6,
          }}
        />
      )}
    </div>
  );
});

export default EquationBlock;
