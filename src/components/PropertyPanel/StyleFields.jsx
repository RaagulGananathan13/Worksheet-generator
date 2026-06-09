import { memo } from 'react';
import useWorksheetStore from '../../store/worksheetStore';
import ColorPicker from './ColorPicker';

/**
 * Style editing fields: font-size, font-weight, color, background, text-align, border-radius.
 * Only renders fields that exist in the block's styles object.
 */
const StyleFields = memo(function StyleFields({ block }) {
  const updateBlockStyles = useWorksheetStore((s) => s.updateBlockStyles);

  const update = (key, value) => {
    updateBlockStyles(block.id, { [key]: value });
  };

  const s = block.styles;

  return (
    <div className="space-y-2.5">
      {s.fontSize !== undefined && (
        <div className="flex items-center gap-2">
          <label className="text-[10px] text-surface-500 w-16 shrink-0">Font Size</label>
          <input
            type="number"
            value={s.fontSize}
            onChange={(e) => update('fontSize', parseFloat(e.target.value) || 16)}
            className="input-field flex-1 text-xs py-1"
          />
          <span className="text-[10px] text-surface-600">px</span>
        </div>
      )}

      {s.fontWeight !== undefined && (
        <div className="flex items-center gap-2">
          <label className="text-[10px] text-surface-500 w-16 shrink-0">Weight</label>
          <select
            value={s.fontWeight}
            onChange={(e) => update('fontWeight', e.target.value)}
            className="input-field flex-1 text-xs py-1"
          >
            {['300', '400', '500', '600', '700', '800'].map((w) => (
              <option key={w} value={w}>{w}</option>
            ))}
          </select>
        </div>
      )}

      {s.color !== undefined && (
        <ColorPicker
          label="Color"
          value={s.color}
          onChange={(v) => update('color', v)}
        />
      )}

      {s.backgroundColor !== undefined && (
        <ColorPicker
          label="Background"
          value={s.backgroundColor}
          onChange={(v) => update('backgroundColor', v)}
        />
      )}

      {s.textAlign !== undefined && (
        <div className="flex items-center gap-2">
          <label className="text-[10px] text-surface-500 w-16 shrink-0">Align</label>
          <select
            value={s.textAlign}
            onChange={(e) => update('textAlign', e.target.value)}
            className="input-field flex-1 text-xs py-1"
          >
            {['left', 'center', 'right'].map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </div>
      )}

      {s.borderRadius !== undefined && (
        <div className="flex items-center gap-2">
          <label className="text-[10px] text-surface-500 w-16 shrink-0">Radius</label>
          <input
            type="number"
            value={s.borderRadius}
            onChange={(e) => update('borderRadius', parseFloat(e.target.value) || 0)}
            className="input-field flex-1 text-xs py-1"
          />
          <span className="text-[10px] text-surface-600">px</span>
        </div>
      )}

      {s.optionBg !== undefined && (
        <ColorPicker
          label="Option BG"
          value={s.optionBg}
          onChange={(v) => update('optionBg', v)}
        />
      )}
    </div>
  );
});

export default StyleFields;
