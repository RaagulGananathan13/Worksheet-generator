import { memo, useRef, useEffect } from 'react';
import Moveable from 'react-moveable';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Wraps a single block element with Moveable for drag/resize.
 * Uses direct DOM manipulation during drag for performance,
 * then commits to Zustand store on drag/resize end.
 */
const BlockWrapper = memo(function BlockWrapper({ blockId, children, isSelected, zoom }) {
  const targetRef = useRef(null);
  const moveableRef = useRef(null);

  const updateBlockPosition = useWorksheetStore((s) => s.updateBlockPosition);
  const updateBlockSize = useWorksheetStore((s) => s.updateBlockSize);
  const blocks = useWorksheetStore((s) => s.blocks);

  const block = blocks.find((b) => b.id === blockId);
  const isLocked = block?.meta?.locked || false;

  // Update moveable when selection changes
  useEffect(() => {
    if (moveableRef.current) {
      moveableRef.current.updateRect();
    }
  }, [isSelected, block?.position, block?.size]);

  if (!isSelected) return children;

  return (
    <>
      {children}
      <Moveable
        ref={moveableRef}
        target={targetRef.current || document.querySelector(`[data-block-id="${blockId}"]`)}
        zoom={1 / (zoom || 1)}
        draggable={!isLocked}
        resizable={!isLocked}
        snappable={true}
        snapDirections={{
          left: true, top: true, right: true, bottom: true,
          center: true, middle: true,
        }}
        elementSnapDirections={{
          left: true, top: true, right: true, bottom: true,
          center: true, middle: true,
        }}
        isDisplaySnapDigit={true}
        snapGap={true}
        snapThreshold={5}
        renderDirections={['nw', 'n', 'ne', 'w', 'e', 'sw', 's', 'se']}

        onDrag={({ target, left, top }) => {
          target.style.left = `${left}px`;
          target.style.top = `${top}px`;
        }}
        onDragEnd={({ target }) => {
          const id = target.dataset.blockId;
          if (id) {
            updateBlockPosition(id, parseFloat(target.style.left), parseFloat(target.style.top));
          }
        }}

        onResize={({ target, width, height, drag }) => {
          target.style.width = `${width}px`;
          target.style.height = `${height}px`;
          target.style.left = `${drag.left}px`;
          target.style.top = `${drag.top}px`;
        }}
        onResizeEnd={({ target, lastEvent }) => {
          const id = target.dataset.blockId;
          if (id && lastEvent) {
            updateBlockSize(id, lastEvent.width, lastEvent.height);
            updateBlockPosition(id, parseFloat(target.style.left), parseFloat(target.style.top));
          }
        }}
      />
    </>
  );
});

export default BlockWrapper;
