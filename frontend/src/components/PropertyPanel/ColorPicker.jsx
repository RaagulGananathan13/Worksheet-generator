import { memo } from 'react';

/**
 * Inline color picker with color input + hex text input.
 * Handles 'transparent' values gracefully.
 */
const ColorPicker = memo(function ColorPicker({ label, value, onChange }) {
  const displayValue = (!value || value === 'transparent' || value === 'rgba(0, 0, 0, 0)')
    ? '#ffffff'
    : value;

  const isTransparent = !value || value === 'transparent' || value === 'rgba(0, 0, 0, 0)';

  return (
    <div className="flex items-center gap-2">
      <label className="text-[10px] text-surface-500 w-16 shrink-0">{label}</label>
      <div className="relative">
        <input
          type="color"
          value={displayValue}
          onChange={(e) => onChange(e.target.value)}
          className="w-7 h-7 rounded border border-surface-700 cursor-pointer bg-transparent p-0 appearance-none"
          style={{
            backgroundColor: isTransparent ? 'transparent' : value,
          }}
        />
        {isTransparent && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="w-5 h-px bg-danger-400 rotate-45" />
          </div>
        )}
      </div>
      <input
        type="text"
        value={value || 'transparent'}
        onChange={(e) => onChange(e.target.value)}
        className="input-field w-20 text-xs py-1 font-mono"
        placeholder="#000000"
      />
    </div>
  );
});

export default ColorPicker;
