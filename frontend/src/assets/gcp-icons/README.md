# Google Cloud icons

These SVGs come from Google Cloud's official architecture icon set (the flat `svg/` icons
Google publishes for architecture diagrams, held locally at
`images-web/gcp_architecture_icons`). They are copied unmodified, and only the icons
`gcpServiceIcons.generated.ts` references are kept here (020, FR-014).

Google publishes these icons for use in diagrams of systems built on Google Cloud. Don't modify
them or use them to suggest Google endorses this app. Google's brand and trademark guidelines
apply.

Don't edit or add files here by hand. Change the overrides in
`backend/scripts/generate_provider_service_icon_map.py` and re-run:

```
cd backend && uv run python scripts/generate_provider_service_icon_map.py --provider gcp \
    --icons ../../images-web/gcp_architecture_icons
```
