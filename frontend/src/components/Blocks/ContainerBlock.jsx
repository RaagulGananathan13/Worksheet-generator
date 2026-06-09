import { memo } from 'react';

/**
 * Renders a container block (grid/flex group).
 * Shown as a dashed outline to indicate grouping.
 */
const ContainerBlock = memo(function ContainerBlock({ block }) {
  const layout = block.content?.layout;

  return (
    <div
      className="w-full h-full border border-dashed border-gray-300/40 rounded bg-transparent
                 flex items-center justify-center"
      title={`Container: ${layout?.type || 'unknown'} layout${layout?.columns ? `, ${layout.columns} columns` : ''}`}
    >
      <span className="text-[10px] text-gray-400/60 pointer-events-none select-none">
        {layout?.type === 'grid' ? `Grid ${layout.columns || ''}col` : 'Flex'}
      </span>
    </div>
  );
});

export default ContainerBlock;
