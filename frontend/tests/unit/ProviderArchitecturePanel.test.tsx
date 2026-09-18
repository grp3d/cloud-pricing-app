import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ArchitectureSummary, Provider } from "../../src/api/client";
import {
  ProviderArchitecturePanel,
  type ProviderArchitecturePanelProps,
} from "../../src/components/workspace/ProviderArchitecturePanel";
import { TooltipProvider } from "../../src/components/ui/tooltip";

function panel(props: ProviderArchitecturePanelProps) {
  return (
    <TooltipProvider>
      <ProviderArchitecturePanel {...props} />
    </TooltipProvider>
  );
}

const providers: Provider[] = [{ code: "aws", name: "AWS", active: true }];

const longName =
  "A very long architecture name that will not fit on one line at a narrow panel width";

function architecture(overrides: Partial<ArchitectureSummary> = {}): ArchitectureSummary {
  return {
    id: "arch-1",
    name: longName,
    provider: "aws",
    created_at: "2026-01-01T00:00:00Z",
    is_public: false,
    ...overrides,
  };
}

const noop: Omit<ProviderArchitecturePanelProps, "architectures" | "width"> = {
  providers,
  selectedProvider: "aws",
  onSelectProvider: vi.fn(),
  architecturesLoading: false,
  architecturesError: null,
  onRetryArchitectures: vi.fn(),
  selectedArchitectureId: undefined,
  onSelectArchitecture: vi.fn(),
  newArchitectureName: "",
  onNewArchitectureNameChange: vi.fn(),
  onCreateArchitecture: vi.fn(),
  isCreatingArchitecture: false,
  onDeleteArchitecture: vi.fn(),
  actionError: null,
  onDismissActionError: vi.fn(),
  isGuest: false,
  onToggleArchitecturePublic: vi.fn(),
  onOpenImportDialog: vi.fn(),
};

function renderPanel(overrides: Partial<ProviderArchitecturePanelProps> = {}) {
  const props: ProviderArchitecturePanelProps = {
    ...noop,
    architectures: [architecture()],
    width: 250,
    ...overrides,
  };
  return render(panel(props));
}

// jsdom does not compute real CSS layout (no box sizes, no overflow clipping), so a
// `.toBeInTheDocument()` check on its own can't tell a visually-clipped control apart from
// a properly-visible one — none of these elements are ever conditionally removed from the
// tree based on `width`, only clipped by CSS at certain widths. These tests instead assert
// the structural (className) guarantees that prevent that clipping, per research.md: the
// create-form row and each architecture row must be allowed to wrap (`flex-wrap`) so a
// fixed-size control that no longer fits beside its sibling relocates to a new line instead
// of being clipped or scrolled out of view. Real visual confirmation is the manual
// quickstart.md walkthrough (T011).
describe("ProviderArchitecturePanel — narrow-width layout", () => {
  it("lets the create-form row wrap so the Create button is never clipped, and keeps the name input from shrinking to nothing", () => {
    renderPanel({ width: 56 });

    const input = screen.getByPlaceholderText("New Architecture name");
    const form = input.closest("form");
    expect(form).not.toBeNull();
    expect(form!.className).toContain("flex-wrap");
    expect(input.className).not.toContain("min-w-0");

    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
  });

  it("lets each architecture row wrap so its share/delete buttons are never clipped", () => {
    renderPanel({ width: 56 });

    const deleteButton = screen.getByRole("button", { name: `Delete ${longName}` });
    const row = deleteButton.closest("li");
    expect(row).not.toBeNull();
    expect(row!.className).toContain("flex-wrap");

    expect(screen.getByRole("button", { name: "Import an architecture" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: `Make ${longName} public` }),
    ).toBeInTheDocument();
  });

  it("wraps a long architecture name instead of truncating it with an ellipsis, and lets the row grow to fit it", () => {
    renderPanel({ width: 56 });

    const nameButton = screen.getByRole("button", { name: longName });
    expect(nameButton).toBeInTheDocument();
    expect(nameButton.className).not.toContain("truncate");
    expect(nameButton.className).toContain("whitespace-normal");
    // The shared Button component's "sm" size fixes a single-line height (h-7); a wrapped
    // multi-line name needs an explicit height override or it overflows/overlaps the next
    // row instead of growing the row to fit (caught via manual browser verification, not
    // by this jsdom suite — jsdom doesn't compute real box heights either).
    expect(nameButton.className).toContain("h-auto");
  });
});
