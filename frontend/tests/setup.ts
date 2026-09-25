import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver; components that measure themselves (PricingPanel's price lines)
// and Radix's tooltip positioning both need one to mount.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
