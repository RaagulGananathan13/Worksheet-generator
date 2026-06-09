export const BLOCK_TYPES = {
  QUESTION_CARD: 'questionCard',
  EQUATION_BLOCK: 'equationBlock',
  IMAGE_BLOCK: 'imageBlock',
  TEXT_BLOCK: 'textBlock',
  OPTION_BLOCK: 'optionBlock',
  CONTAINER_BLOCK: 'containerBlock',
  TITLE_BLOCK: 'titleBlock',
  GENERIC_BLOCK: 'genericBlock',
};

export const DEFAULT_SIZES = {
  [BLOCK_TYPES.QUESTION_CARD]: { width: 260, height: 200 },
  [BLOCK_TYPES.EQUATION_BLOCK]: { width: 420, height: 50 },
  [BLOCK_TYPES.IMAGE_BLOCK]: { width: 110, height: 110 },
  [BLOCK_TYPES.TEXT_BLOCK]: { width: 200, height: 40 },
  [BLOCK_TYPES.OPTION_BLOCK]: { width: 52, height: 44 },
  [BLOCK_TYPES.CONTAINER_BLOCK]: { width: 800, height: 600 },
  [BLOCK_TYPES.TITLE_BLOCK]: { width: 400, height: 60 },
  [BLOCK_TYPES.GENERIC_BLOCK]: { width: 200, height: 100 },
};

export const ZOOM_LIMITS = { min: 0.25, max: 2, step: 0.1 };

export const SNAP_THRESHOLD = 5;

export const HISTORY_LIMIT = 50;
