/**
 * Chinese clinical text commonly uses a single tilde for numeric ranges
 * (for example, `2~3次`).  GFM's optional single-tilde delete syntax turns
 * that notation into a misleading strikethrough, so only explicit `~~` is
 * treated as deletion throughout the product.
 */
export const MARKDOWN_GFM_OPTIONS = {
  singleTilde: false,
} as const;
