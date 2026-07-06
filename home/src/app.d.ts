// Per-route PageData is inferred from each route's own load function via
// ./$types, so the App.PageData augmentation is intentionally left empty:
// the landing returns { home } while story pages return { scenario }.
declare global {
  namespace App {}
}

export {};
