/**
 * Download filename for an Admin architecture export (014-architecture-templates-import-export,
 * spec FR-013): `<username>_<YYYYMMDDTHHMMSS>.json`, using the admin's local clock at the moment
 * of download. Characters outside `[A-Za-z0-9._-]` become `_` so the name is safe on every
 * common desktop filesystem.
 */
export function buildExportFilename(username: string, now: Date): string {
  const safeUsername = username.replace(/[^A-Za-z0-9._-]/g, "_");
  const pad = (n: number) => String(n).padStart(2, "0");
  const timestamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `T${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `${safeUsername}_${timestamp}.json`;
}
