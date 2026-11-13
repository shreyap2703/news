interface ImportMetaEnv {
  /** Supabase project URL, for example https://abcdefghijklmnop.supabase.co. */
  readonly VITE_SUPABASE_URL?: string
  /** Supabase publishable (or legacy anon) key. It is meant for browsers; Row Level Security protects the data. */
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
