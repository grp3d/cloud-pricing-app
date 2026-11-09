/** 021 US5 (FR-035): shared classes for controls on the dark header band. */

/** Hover, focus and pressed states for the header's links and buttons, on its dark band. */
export const HEADER_CONTROL =
  "inline-flex h-8 items-center gap-1 rounded-md px-2.5 text-sm font-medium text-header-muted-foreground transition-colors duration-150 hover:bg-header-accent hover:text-header-foreground active:bg-header-accent/70";

/** The current page: a fill plus a blue underline, so it doesn't rely on colour alone. */
export const HEADER_CURRENT =
  "bg-header-accent text-header-foreground shadow-[inset_0_-2px_0_var(--header-ring)] hover:bg-[color-mix(in_oklch,var(--header-accent),var(--header-foreground)_8%)]";
