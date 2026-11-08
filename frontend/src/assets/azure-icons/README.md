# Microsoft Azure icons

These SVGs come from Microsoft's official Azure architecture icon set (Azure Public Service Icons,
held locally at `images-web/azure_architecture_icons`). The file contents are copied unmodified,
and only the icons `azureServiceIcons.generated.ts` references are kept here (020, FR-014). Each
file is saved under its icon name, without the package's number prefix
(`10021-icon-service-Virtual-Machine.svg` → `Virtual-Machine.svg`).

Microsoft's terms of use (`Microsoft_Terms_of_Use.pdf` and `Azure_Icons_FAQ.pdf` in the package)
allow these icons in architecture diagrams and documentation. Don't modify, crop or recolour them,
and don't use them in a way that suggests Microsoft endorses this app.

Don't edit or add files here by hand. Change the overrides in
`backend/scripts/generate_provider_service_icon_map.py` and re-run:

```
cd backend && uv run python scripts/generate_provider_service_icon_map.py --provider azure \
    --icons ../../images-web/azure_architecture_icons
```
