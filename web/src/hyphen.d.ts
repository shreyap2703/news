declare module 'hyphen/en' {
  /** Returns the text with soft hyphens (U+00AD) at every point where its English words may break. */
  export function hyphenateSync(text: string, options?: { hyphenChar?: string; minWordLength?: number }): string
}
