import { memo } from 'react';

/**
 * Renders a standalone image block with configurable object-fit.
 */
const ImageBlock = memo(function ImageBlock({ block }) {
  return (
    <img
      src={block.content.src}
      alt={block.content.alt || ''}
      className="w-full h-full"
      style={{
        objectFit: block.styles.objectFit || 'contain',
        borderRadius: block.styles.borderRadius || 0,
      }}
      draggable={false}
    />
  );
});

export default ImageBlock;
