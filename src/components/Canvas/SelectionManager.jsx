import { useRef } from 'react';
import Selecto from 'react-selecto';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Manages rubber-band multi-selection of blocks on the canvas.
 * Uses react-selecto to detect selection via click and drag-select.
 */
export default function SelectionManager({ containerRef }) {
  const selectoRef = useRef(null);
  const setSelectedBlockIds = useWorksheetStore((s) => s.setSelectedBlockIds);
  const selectedBlockIds = useWorksheetStore((s) => s.selectedBlockIds);

  return (
    <Selecto
      ref={selectoRef}
      container={containerRef?.current}
      dragContainer={containerRef?.current}
      selectableTargets={['.worksheet-block']}
      selectByClick={false}
      selectFromInside={false}
      toggleContinueSelect={'shift'}
      hitRate={0}
      onSelectEnd={({ selected }) => {
        const ids = selected
          .map((el) => el.dataset.blockId)
          .filter(Boolean);
        if (ids.length > 0) {
          setSelectedBlockIds(ids);
        }
      }}
    />
  );
}
