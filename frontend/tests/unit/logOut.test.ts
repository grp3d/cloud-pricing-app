import { beforeEach, describe, expect, it } from "vitest";

import { api } from "../../src/api/client";

/** 027 US3 (FR-008, FR-009, research R5): Log out returns the browser to its guest. */

const GUEST_KEY = "cloud-pricing-guest-id";
const CURRENT_KEY = "cloud-pricing-current-identity-id";

beforeEach(() => localStorage.clear());

describe("api.logOut", () => {
  it("returns to the guest this browser had before logging in", () => {
    localStorage.setItem(GUEST_KEY, "guest-1");
    localStorage.setItem(CURRENT_KEY, "user-1");
    api.logOut();
    expect(localStorage.getItem(CURRENT_KEY)).toBe("guest-1");
    expect(localStorage.getItem(GUEST_KEY)).toBe("guest-1");
  });

  it("creates and uses a new guest when none is recorded", () => {
    localStorage.setItem(CURRENT_KEY, "user-1");
    api.logOut();
    const guest = localStorage.getItem(GUEST_KEY);
    expect(guest).toMatch(/^[0-9a-f-]{36}$/);
    expect(localStorage.getItem(CURRENT_KEY)).toBe(guest);
  });

  it("never overwrites the recorded guest", () => {
    localStorage.setItem(GUEST_KEY, "guest-1");
    localStorage.setItem(CURRENT_KEY, "user-1");
    api.logOut();
    api.logOut();
    expect(localStorage.getItem(GUEST_KEY)).toBe("guest-1");
  });
});
