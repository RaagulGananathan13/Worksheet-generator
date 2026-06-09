import { memo } from 'react';
import useWorksheetStore from '../../store/worksheetStore';
import { BLOCK_TYPES } from '../../utils/constants';

/**
 * Type-specific content editing fields.
 * Adapts to the block type automatically.
 */
const ContentFields = memo(function ContentFields({ block }) {
  switch (block.type) {
    case BLOCK_TYPES.QUESTION_CARD:
      return <QuestionCardContent block={block} />;
    case BLOCK_TYPES.EQUATION_BLOCK:
      return <EquationContent block={block} />;
    case BLOCK_TYPES.IMAGE_BLOCK:
      return <ImageContent block={block} />;
    case BLOCK_TYPES.TEXT_BLOCK:
    case BLOCK_TYPES.TITLE_BLOCK:
      return <TextContent block={block} />;
    case BLOCK_TYPES.OPTION_BLOCK:
      return <OptionContent block={block} />;
    case BLOCK_TYPES.GENERIC_BLOCK:
      return <GenericContent block={block} />;
    default:
      return (
        <p className="text-xs text-surface-500 italic">No editable content for this block type</p>
      );
  }
});

function EquationContent({ block }) {
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);
  const updateBlockStyles = useWorksheetStore((s) => s.updateBlockStyles);

  return (
    <div className="space-y-3">
      <Field label="Prefix">
        <input
          type="text"
          value={block.content.prefix || ''}
          onChange={(e) => updateBlockContent(block.id, { prefix: e.target.value })}
          className="input-field w-full text-xs"
        />
      </Field>
      <Field label="Equation">
        <input
          type="text"
          value={block.content.equation || ''}
          onChange={(e) => updateBlockContent(block.id, { equation: e.target.value })}
          className="input-field w-full text-xs"
        />
      </Field>
      <div className="flex items-center gap-2">
        <label className="text-[10px] text-surface-400 uppercase tracking-wider flex-1">Answer Box</label>
        <button
          onClick={() => updateBlockContent(block.id, { hasAnswerBox: !block.content.hasAnswerBox })}
          className={`px-2.5 py-1 text-[10px] rounded font-medium transition-colors ${
            block.content.hasAnswerBox
              ? 'bg-accent-500/20 text-accent-400'
              : 'bg-surface-800 text-surface-500'
          }`}
        >
          {block.content.hasAnswerBox ? 'ON' : 'OFF'}
        </button>
      </div>
      {block.content.hasAnswerBox && (
        <div className="grid grid-cols-2 gap-2">
          <Field label="Box W">
            <input
              type="number"
              value={block.content.answerBoxSize?.width || 85}
              onChange={(e) => updateBlockContent(block.id, {
                answerBoxSize: { ...(block.content.answerBoxSize || {}), width: parseFloat(e.target.value) || 85 }
              })}
              className="input-field w-full text-xs py-1"
            />
          </Field>
          <Field label="Box H">
            <input
              type="number"
              value={block.content.answerBoxSize?.height || 48}
              onChange={(e) => updateBlockContent(block.id, {
                answerBoxSize: { ...(block.content.answerBoxSize || {}), height: parseFloat(e.target.value) || 48 }
              })}
              className="input-field w-full text-xs py-1"
            />
          </Field>
        </div>
      )}
    </div>
  );
}

function QuestionCardContent({ block }) {
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);

  return (
    <div className="space-y-3">
      {block.content.image && (
        <Field label="Image URL">
          <input
            type="text"
            value={block.content.image.src || ''}
            onChange={(e) =>
              updateBlockContent(block.id, {
                image: { ...block.content.image, src: e.target.value },
              })
            }
            className="input-field w-full text-xs"
          />
        </Field>
      )}
      <Field label="Word">
        <input
          type="text"
          value={block.content.word || ''}
          onChange={(e) => updateBlockContent(block.id, { word: e.target.value })}
          className="input-field w-full text-xs"
        />
      </Field>
      {block.content.options && (
        <Field label={`Options (${block.content.options.length})`}>
          {block.content.options.map((opt, i) => (
            <div key={opt.id} className="flex items-center gap-1 mb-1.5">
              <span className="text-[10px] text-surface-600 w-4">{i + 1}.</span>
              <input
                type="text"
                value={opt.label}
                onChange={(e) => {
                  const updated = [...block.content.options];
                  updated[i] = { ...opt, label: e.target.value };
                  updateBlockContent(block.id, { options: updated });
                }}
                className="input-field flex-1 text-xs py-1"
              />
            </div>
          ))}
        </Field>
      )}
    </div>
  );
}

function ImageContent({ block }) {
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);
  const updateBlockStyles = useWorksheetStore((s) => s.updateBlockStyles);

  return (
    <div className="space-y-3">
      <Field label="Source URL">
        <input
          type="text"
          value={block.content.src || ''}
          onChange={(e) => updateBlockContent(block.id, { src: e.target.value })}
          className="input-field w-full text-xs"
        />
      </Field>
      <Field label="Alt Text">
        <input
          type="text"
          value={block.content.alt || ''}
          onChange={(e) => updateBlockContent(block.id, { alt: e.target.value })}
          className="input-field w-full text-xs"
        />
      </Field>
      <div className="flex items-center gap-2">
        <label className="text-[10px] text-surface-500 w-16 shrink-0">Object Fit</label>
        <select
          value={block.styles.objectFit || 'contain'}
          onChange={(e) => updateBlockStyles(block.id, { objectFit: e.target.value })}
          className="input-field flex-1 text-xs py-1"
        >
          {['contain', 'cover', 'fill', 'none', 'scale-down'].map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

function TextContent({ block }) {
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);

  return (
    <Field label="Text Content">
      <textarea
        value={block.content.text || ''}
        onChange={(e) => updateBlockContent(block.id, { text: e.target.value })}
        className="input-field w-full text-xs resize-none"
        rows={3}
      />
    </Field>
  );
}

function OptionContent({ block }) {
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);

  return (
    <Field label="Label">
      <input
        type="text"
        value={block.content.label || ''}
        onChange={(e) => updateBlockContent(block.id, { label: e.target.value })}
        className="input-field w-full text-xs"
      />
    </Field>
  );
}

function GenericContent({ block }) {
  const updateBlockContent = useWorksheetStore((s) => s.updateBlockContent);

  return (
    <div className="space-y-3">
      <Field label="Text Content">
        <textarea
          value={block.content.text || ''}
          onChange={(e) => updateBlockContent(block.id, { text: e.target.value })}
          className="input-field w-full text-xs resize-none"
          rows={3}
        />
      </Field>
      {block.content.innerHTML && (
        <p className="text-[10px] text-surface-500 italic">
          This block preserves original HTML layout
        </p>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="text-[10px] text-surface-400 uppercase tracking-wider mb-1 block">{label}</label>
      {children}
    </div>
  );
}

export default ContentFields;
