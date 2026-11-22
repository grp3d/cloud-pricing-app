# Contract: Preferences API (`appearance` section)

Extends 019's `GET` / `PATCH /me/preferences`. Everything else is unchanged.

## GET /me/preferences

```json
{ "schema_version": 1,
  "data": { "migrated_from_browser": true, "workspace": { … },
            "appearance": { "theme": "dark" } } }
```

`appearance` is omitted when never set (light).

## PATCH /me/preferences

| Body | Logged-in user | Guest |
|---|---|---|
| `{ "appearance": { "theme": "dark" } }` | 200, saved | 403 `{"detail": "theme_not_saved_for_guests"}`, nothing saved |
| `{ "appearance": null }` | 200, cleared (light) | 403, as above |
| `{ "appearance": { "theme": "blue" } }` | 422 | 422 |
| `{ "appearance": { "theme": "dark", "x": 1 } }` | 422 (strict) | 422 |
| a patch without `appearance` | unchanged behaviour | unchanged behaviour |

A guest is a user with no username.
