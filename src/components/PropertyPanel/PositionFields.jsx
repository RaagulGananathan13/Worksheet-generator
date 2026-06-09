import { memo } from 'react';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Position and size fields for the selected block: X, Y, Width, Height.
 */
const PositionFields = memo(function PositionFields({ block }) {
  const updateBlockPosition = useWorksheetStore((s) => s.updateBlockPosition);
  const updateBlockSize = useWorksheetStore((s) => s.updateBlockSize);

  return (
    <div className="grid grid-cols-2 gap-2">
      <NumberField
        label="X"
        value={Math.round(block.position.x)}
        onChange={(v) => updateBlockPosition(block.id, v, block.position.y)}
      />
      <NumberField
        label="Y"
        value={Math.round(block.position.y)}
        onChange={(v) => updateBlockPosition(block.id, block.position.x, v)}
      />
      <NumberField
        label="W"
        value={Math.round(block.size.width)}
        onChange={(v) => updateBlockSize(block.id, v, block.size.height)}
      />
      <NumberField
        label="H"
        value={Math.round(block.size.height)}
        onChange={(v) => updateBlockSize(block.id, block.size.width, v)}
      />
    </div>
  );
});

function NumberField({ label, value, onChange }) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-[10px] text-surface-500 w-4 shrink-0 font-medium">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="input-field flex-1 text-xs py-1 w-full"
      />
    </div>
  );
}

export default PositionFields;
