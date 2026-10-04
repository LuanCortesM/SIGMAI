# SIGMAI Cartographic Rules and Standards

## Plugin Authorship Vs Generated Map Authorship

SIGMAI is a public QGIS plugin. Its plugin author is not automatically the author of every map generated with the tool.

Plugin authorship appears in:

- `metadata.txt`
- README and institutional documentation
- About/HUD interface
- SIGMAI technical reports
- package and plugin repository metadata

Plugin author:

- MACIEL, L. S. C.
- herpetomantiqueira@gmail.com
- Developed by Luan da Silva Cortes Maciel as a Master's research product linked to the Escola Nacional de Botanica Tropical and Jardim Botanico do Rio de Janeiro, under the supervision of Leandro Freitas.
- Associated project: Herpeto Mantiqueira.

Generated map authorship belongs to:

1. the `map_author` provided in the command;
2. the configured SIGMAI user profile;
3. the QGIS project metadata, when available;
4. or a generic software credit when no author is specified.

Default public map credit:

`Elaborado com SIGMAI - Secure GIS-AI Interface/QGIS.`

Correct example:

`Fonte: IBGE, 2025. Elaboracao: Nome do Usuario. Criado com SIGMAI/QGIS.`

Incorrect public default:

`Author: MACIEL, L. S. C.`

MACIEL, L. S. C. can appear as map author only when explicitly provided as `map_author` or in development/test mode with explicit fallback enabled.
