export const DEFAULT_ACTIVITY_WINDOW = 100;

export interface ActivityWindow<T> {
  visible: T[];
  hiddenCount: number;
  totalCount: number;
}

/**
 * Bounds the initial activity DOM without truncating the Node projection.
 * Older records can be revealed explicitly by the operator.
 */
export function activityWindow<T>(items: readonly T[], limit = DEFAULT_ACTIVITY_WINDOW): ActivityWindow<T> {
  const boundedLimit = Number.isSafeInteger(limit) && limit > 0 ? limit : DEFAULT_ACTIVITY_WINDOW;
  const start = Math.max(0, items.length - boundedLimit);
  return {
    visible: items.slice(start),
    hiddenCount: start,
    totalCount: items.length,
  };
}
