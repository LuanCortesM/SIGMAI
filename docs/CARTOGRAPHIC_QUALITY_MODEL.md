# The cartographic quality model

## The problem this replaces

Version 0.1.1 evaluated a generated map by checking whether items existed in the layout. If `main_map`, `title`, `legend`, `scale_bar`, `north_arrow` and `source` were all present and the exported file was above a size floor, the map was graded **A — Professional map** with zero warnings.

Here is a map that received exactly that grade:

- The **north arrow** was the letter `N` with a caret below it, set as a text label. A label does not rotate with the map, so the moment the frame is rotated or the projection has meridian convergence, the arrow is simply wrong.
- The **scale bar** read `0 1 2 km` on a map covering 41 km. The bar spanned about 4% of the frame — too short to estimate any distance from.
- The **legend** listed one of the three layers drawn. Drainage and occurrence points were on the map and absent from the legend, so a reader could see features and had no way to know what they were.
- There was **no coordinate grid**, despite `include_grid=True`. The grid was enabled without an interval, and the QGIS default interval is `0.0`, so nothing was drawn. The orchestrator still reported the grid as created.
- There was **no numeric scale, no datum declaration and no date**.

None of this is exotic. Each item would be caught in the first minute of a review. The evaluator missed all of it because it was asking the wrong question: not *is this map correct?* but *are the boxes present?*

That mattered more than it would in a manual tool, because the grade was the **only feedback an AI assistant received**. Told that its output was a professional map with no warnings, an assistant has no reason to look again. The feedback loop was not merely weak; it actively asserted the opposite of the truth.

## What replaces it

An explicit rulebook of 43 rules across ten categories. Each rule carries:

| Field | Purpose |
|---|---|
| `id` | Stable identifier, e.g. `CART020` |
| `severity` | `error` (the map is wrong), `warning` (defective but usable), `advice` (could be better) |
| `rationale_pt` | Why the rule exists, stated as a consequence for the reader of the map |
| `fix_pt` | The SIGMAI command that satisfies it — this is the string the assistant acts on |
| `reference` | The standard, textbook or documentation the rule rests on |

The rulebook is available to assistants as data through `sigmai_cartographic_rulebook`, so the rules can be read *before* composing rather than discovered by failing.

## Categories

| Category | Covers |
|---|---|
| `elementos` | Title, legend, whether the legend explains every visible layer, whether its content fits its box, and whether the labels asked for were actually placed |
| `escala` | Scale bar presence, proportion, unit validity for the CRS, numeric scale |
| `orientacao` | Orientation indicated, and by a symbol rather than a text label |
| `procedencia` | Source, authorship, reference system, production date |
| `grade` | Coordinate grid enabled, with a non-zero interval, annotated |
| `geometria` | Items inside the page and margins, no overlaps, map dominance |
| `tipografia` | Minimum printable font size, title/subtitle hierarchy, and the same check at the final printed width of a journal figure |
| `projecao` | Projected CRS where metric measurement is claimed |
| `dados` | Extent contains the data, frame is not blank, the data occupy the frame, output written; coordinates fit the declared reference system; the extent is not stretched by a few isolated points |
| `simbologia` | Layer colours remain distinguishable under simulated colour-vision deficiency; a greyscale figure has no colour; the subject is not hidden under other layers; point symbols do not hide how many records fall in one place; a raster colour ramp is not stretched by a fill value or a spike; a heatmap does not hide most places that have points |

## Grading

Each failed rule subtracts from 100: 15 for an error, 5 for a warning, 1.5 for advice.

| Grade | Condition | Meaning |
|---|---|---|
| A | no errors, score ≥ 92 | Publishable |
| B | no errors, score ≥ 80 | Usable, minor adjustments pending |
| C | ≤ 1 error, score ≥ 62 | Incomplete: a required element is missing |
| D | score ≥ 40 | Defective on several counts |
| E | below that | Invalid |

Applying the rulebook to the map described above gives **E — invalid**, 4/100, with three blocking errors: the legend does not explain two of three visible layers (`CART020`), the grid has interval zero and renders nothing (`CART026`), and the reference system is never declared (`CART008`). Alongside them, five warnings including the text north arrow (`CART025`) and the 4% scale bar (`CART022`).

The same map, composed by the current engine, scores **A — 100/100**.

## Blank-frame detection

`CART062` is the only rule that looks at pixels. After a PNG export, the engine samples a grid of points inside the map frame and measures the fraction that is not background. A blank frame with a successful export is the most dangerous failure mode available, because every return code says success: the command succeeded, the file exists, the file is large enough, and the map is empty. Extent in the wrong CRS, an invisible layer, or a layer whose source moved all produce it.

Five more rules read the rendered image, the labelling engine or the legend renderer, all added in 1.1.0 after the "raw PyQGIS × SIGMAI" experiment (`docs/experiments/2026-09-06_pyqgis_direto_vs_sigmai/`) showed what a plain element checklist misses:

- **`CART068` — labels placed.** The map is rendered once more with `QgsLabelingEngineSettings.CollectUnplacedLabels`, and every label the engine could not place is counted per layer. A layer with 207 site names and room for 40 produces a map that *looks* labelled and is not; the rule names the layer and the count, and `compose_campaign_map` refuses to label more than 60 points on its own.
- **`CART069` — the frame is occupied.** The frame is divided into a 3 × 3 grid; the area coverage of each cell is computed geometrically from polygons and from the footprint of thematic rasters (up to 5 000 features per layer), and a band counts as empty only if the ink of the data themselves — each layer rendered without grid or labels — is also below 0.05 % — any line or point of data in the band counts (the 2 % threshold of the exported image, which also counts grid and labels, applies only when the layers cannot be rendered one by one): a hydrography map is made of lines and has almost no polygon area. A whole column or row with less than 5 % coverage (2 % ink) means the page shape does not match the data — a tall state on a landscape sheet — and the finding names the band ("west column", "south row"). Total coverage was tried first and rejected: a legitimate state map with a wide margin fails it, an empty band does not lie.
- **`CART070` — colours distinguishable by readers with a colour-vision deficiency.** The fill or stroke colour of each visible layer (and each class of a categorised or graduated renderer) is transformed with the protanopia, deuteranopia and severe-tritanomaly matrices of Machado, Oliveira & Fernandes (2009, *IEEE Transactions on Visualization and Computer Graphics* 15(6), severity 1.0; the authors state that their model is not intended for tritanopia, so the third simulation is the severity-1.0 tritanomaly row of their table) and compared pairwise in CIE L\*a\*b\*; a pair with ΔE\*ab below 15 under any of the three simulations is reported, with the Okabe & Ito (2008) palette offered as the fix. Only colours the reader compares are compared: a polygon without fill is a stroke and competes with lines, by its outline colour, and each hatch pattern is a family of its own, told apart by the pattern.
- **`CART071` — fonts readable at the printed width.** When the composition was asked for as a journal figure (`journal_column`, `figure_width_mm`) or the audit is told `print_width_mm`, every font size is scaled by printed width ÷ page width and compared with the minimum readable size. A 7 pt caption on an A4 page becomes 3 pt in a single-column figure.

- **`CART072` — the legend fits its box.** `QgsLegendRenderer.minimumSize()` gives the size the legend content needs; when the item is not set to resize to contents and the content exceeds the box by more than 0.5 mm, QGIS clips the names at the edge and draws over whatever sits below, without any warning. `compose_map` measures the same thing and, before the audit, shrinks the legend font down to 6 pt and then drops the per-layer sources from the entries (they stay in the credit line and the recipe).
- **`CART073` — a greyscale figure has no colour.** When the composition (`colour_mode: "greyscale"`) or the audit asks for greyscale, the exported raster is sampled on a 300 × 300 grid and the share of inked pixels whose chroma (largest minus smallest RGB channel) is 20 or more is measured; above 0.5 % the rule fails. Journals print in greyscale and charge for colour in print; a colour map converted afterwards loses the distinction between colours of equal lightness, so the greyscale mode composes with four greys at least 18 L* apart, hatching from the fifth polygon layer on, and a black inset outline. A layer that keeps its own style is converted class by class — a graduation from light to dark, categories in the order of their original lightness with hatching beyond six, a paletted raster with one grey per class, any other raster through a luminosity filter — so the thematic map survives the conversion.
- **`CART074` — scale bar labels do not overlap.** Labels sit centred on the divisions, so two neighbours touch when half of each, added, exceeds the segment. Every adjacent pair, at the bar's font size and an average digit width of 0.6 em, must fit its segment with 20 % to spare; the tightest pair is not always the one at the right end ("0.25" and "0.5" need more room than "0.75" and "1"). A single-column figure with 4 + 1 segments of 2.5 mm each wrote "25 0 255075100 km". `compose_map` chooses the segments under the same constraint and, when two do not fit, draws a single one.
- **Covered layers count as phantoms (`CART021`).** The inspector renders each layer of the frame alone, as the frame draws it (its scale, size, DPI and scale-dependent visibility, without labels), and composites the alpha channels top-down: what stays visible of a layer is one minus the cover of the layers above, over the pixels it paints. A layer with less than 10 % of its ink visible that also shows as a patch on less than 1 % of the frame is covered, and listing it in the legend fails the rule; a layer with no feature in the extent is reported as empty, with its own message. A sliver of outline along a border is a line, not a patch, and does not save a covered layer. QGIS draws the first layer of a map item's list on top. The composer draws rasters at the bottom, then polygons, lines and points, the subject above its context, and draws a polygon layer that contains another one of the map (a state over its municipalities) as a heavy outline on top instead of a fill that would hide it.

- **`CART075` — the map subject is visible.** With `subject_layer_id` declared, at least half of what the subject paints must stay visible under the layers drawn above it. An elevation model under opaque municipalities scored A before this rule. The composer draws polygons over a raster subject — or over a point layer drawn as a heatmap, which is a surface too — as outlines. When the cover comes from crowded points, the finding says so and points to smaller, semi-transparent symbols, a heatmap or one proportional symbol per site.
- **`CART076` — point symbols do not hide the count** (warning, 1.3.0). The points of each point layer drawn with fixed-size symbols are taken to millimetres of the frame and binned in cells the size of the symbol; in a cell with *k* points only the first ones change the image — one for an opaque symbol, seven at 35 % opacity, the number of layers that takes the ink to 95 %. The rest are hidden: in the legend and in the count, not on the map. With at least 50 points in the frame and more than half of them hidden, the rule fails. It came from the 362,210 GBIF records of the Itatiaia National Park, which sit on 11,742 distinct coordinates, one of them with 54,009 records: as dots, that place looked like a place with a single record, and a map of 10,000 of those records scored A. Heatmaps and point clusters show the count another way and are not measured. Proportional symbols are measured with their smallest circle: one circle per exact coordinate left 79 % of the Itatiaia sites on top of others at 1:300,000, and the densest place looked the emptiest, so the failure gives the `scale` at which `count_points_by_site` should merge the sites (at least 1 mm apart on paper; there, 11,224 sites become 863 and none is hidden). The fix points to `apply_heatmap_style`, to `count_points_by_site` followed by `apply_proportional_symbol_style`, or to `compose_map` with `dense_points`. Before this rule, the composer itself changed: the palette's point symbol (2.2 mm, near-opaque, outlined) now steps down — 1.6, 1.2, 0.9, 0.6 and 0.45 mm, with decreasing opacity — until at most a quarter of the points is hidden and the symbols cover at most a quarter of the area the points occupy, measured the same way; records repeated on the same coordinates are left to this rule, since no symbol size separates them. The calibration is in `docs/experiments/2026-10-26_pontos_empilhados/`.

Four more rules came from a battery of extreme data run after that one — the same question asked of other extremes, each composed by SIGMAI over the real park and municipalities. All four maps scored A, or failed for an unrelated reason:

- **`CART077` — the raster colour ramp shows the data** (warning). For continuous pseudocolour and stretched grey renderers, the 2nd and 98th percentiles of the pixels in the frame are compared with the ends of the ramp; at least 40 % of the ramp must be in use. A digital elevation model with a block of −32 768 that the file did not declare as no-data had its ramp run from −32 768 to 2 764 m: the relief came out in one colour, the legend announced −32 768 m, and the map scored A. `apply_raster_style` now leaves the known fill values (−32 768, −32 767, −9 999, −99 999, the lowest Float32) out of the ramp, declares them as no-data on the layer (the file is not changed) and stops the ramp at the 0.5/99.5 percentile when an extreme is an isolated spike, saying so in both cases. The fill values are left out of the rule's percentiles too.
- **`CART078` — coordinates fit the declared reference system** (error). Each vector layer is checked against the area of use of its CRS (with 3° to spare); a projected layer whose coordinates all fit between −180 and 180 and −90 and 90 is reported as degrees declared as UTM; points at exactly 0,0 are reported as the value spreadsheets write when the position is missing. Degrees declared as UTM had produced a map at 1:2 near the South Pole, failed only for cutting data.
- **`CART079` — the extent is not stretched by isolated points** (warning). For point layers with 20 points or more, the box of the 1st to 99th percentiles is the core; when the spread of all points exceeds five times the core and the points outside it are few (at most 0.5 %, or 3), the finding names them as a likely coordinate error. One record at 0,0 had turned a park map into a map of the Atlantic.
- **`CART080` — the heatmap shows the places that have points** (warning). Points are counted in cells the size of the heatmap radius; a cell below 2 % of the densest one stays under the transparent start of the ramp. With more than 80 % of the places that have points in that state, the rule fails and points to a lower `max_value` or to one proportional symbol per site. A focus of 20 000 records had hidden 300 others spread over the park (99.6 % of the places below 2 %); the 362 210 GBIF records of the park reach 93 %; the INPE fire hotspots of Piauí, a legitimate density map with a visible pale tail, 55 % — at 10 % and one half, that map was being failed.
- **`CART081` — comparison panels share colour and size scales** (warning). When the same variable is drawn in two or more panels (a heatmap of the same weight, graduated classes of the same field, proportional symbols of the same field), the panels must use the same scale: a heatmap with the automatic maximum stretches each panel to its own peak, so the reddest colour of one is not the reddest of the other. Found while making a figure of the Itatiaia records before and after 2015. The fix points to common `min_value`/`max_value` in `apply_proportional_symbol_style`, the same classes, or the same `max_value` and radius for heatmaps.

The composer also stopped drawing a metric scale bar on a map left in geographic coordinates (the numeric scale stays, and `CART060` still asks for `map_crs`), and thins the palette outline of polygons that are small on paper — 20 000 plots of 150 m at 1:250 000 are 0.6 mm wide, and the 0.35 mm outline had merged them into a solid block. `compose_map` refuses `label_field` on a layer with more than 5 000 features: with 20 000 points the labelling engine dropped 98 % of the labels, labelled an arbitrary subset and took 93 s. A point symbol the composer shrank keeps a legible legend sample (at least 1.6 mm and 70 % opacity), and a graduated classification whose quantiles collapse — counts with many zeros — says so instead of returning one class in silence.

`CART042` (no overlapping items) also changed: an item that sits over a map frame is no longer a defect when the 3 mm ring around it holds less than 3 % ink — a legend or a locator inset over the open sea is a legitimate overlay, and the two states' hand-made maps in the experiment were being failed for it.

## Where the rules come from

Every rule's `reference` names one of three kinds of ground, in this order, and says which:

- **Normative.** Brazil's national cartography regulations, *Decreto nº 89.817/1984* (Instruções Reguladoras das Normas Técnicas da Cartografia Nacional), whose articles 12–21 require a title (art. 12), a legend (13), numeric *and* graphic scale "always" (14), the geodetic references of the projection (15), a kilometric or sexagesimal grid (17), a locator diagram of the sheet within the state, region or country (18), the edition year, field and compilation dates and the producing body (19), SI units (20) and the Brazilian Geodetic System (21); IBGE's *Resolução PR nº 1/2015* (SIRGAS2000 as the sole reference frame); and IBGE's *Noções básicas de cartografia* (1999) for scale forms and UTM zoning. The decree regulates systematic (official) mapping; SIGMAI applies it by analogy to thematic scientific maps, which is what its element rules assume.
- **Academic.** Brewer (2016) *Designing Better Maps* for map elements, visual hierarchy, figure–ground, locator maps and type; Slocum et al. (2009) *Thematic Cartography and Geovisualization* for legend design; Snyder (1987) USGS PP 1395 for projections; Machado, Oliveira & Fernandes (2009) for colour-vision simulation, Robertson (1977) for CIE 1976 L\*a\*b\*/ΔE\*ab and Okabe & Ito (2008) for the palette offered as a fix; PLOS ONE's figure requirements (8–12 pt at final width) and Rodriguésia's author guidelines (7 cm single column, 15 cm page, 300 dpi) for what journals actually ask of a figure.
- **Design decisions.** Where a rule's number comes from SIGMAI itself, the reference says so: the 6 pt floor, 15–45 % of the frame for the scale bar, 5 % coverage (2 % ink) for an empty band, ΔE\*ab < 15, a 0.5 mm legend overflow, 3 % ink in a 3 mm ring around an overlaid item, 10 mm print margins. When a rule is checked through the QGIS API, the reference names that too, after the ground, as `verificação:` — the API says *how* the rule is checked, not *why* it exists.

None of the thresholds was measured with readers. `tools/threshold_sensitivity.py` re-scores 138 test maps while varying each threshold alone and recomputes the composer's own decisions (orientation/arrangement switch gain, publication-series margin, font exponent, panel grid); `docs/experiments/2026-09-19_sensibilidade_limiares/` holds the tables and a reading of them. In short: the scale-bar maximum, map dominance, overlay ink, legend overflow, inset coverage and the error and advice penalties change no grade across wide ranges; the empty-band coverage, the 6 pt floor (coupled to the composer's own floor), the scale-bar minimum and the warning penalty do decide, and are declared as design parameters for that reason; ΔE\*ab < 15 sits inside the only window — (12.1, 16.1) — that flags the three calibration pairs without flagging any pair of Okabe & Ito's palette; and the composer's own polygon palette has four mutually distinguishable fills, after which the audit itself objects. `sigmai_cartographic_rulebook` exposes the thresholds and this provenance to the assistant.

## Testing the rules without QGIS

The rulebook evaluates an *observation* — a plain dictionary describing the layout — not a live QGIS object. `sigmai/cartography/inspector.py` produces observations from real layouts; `rulebook.py` never imports PyQGIS.

The practical consequence is that a rule can be tested in CI, and that a regression can be captured as data. `tests/test_cartographic_rulebook.py` contains the 0.1.1 map as an observation dictionary and asserts that it is rejected. If a future change makes the evaluator lenient again, that test fails.

It also means you can argue with a rule by reading a file. See [CONTRIBUTING.md](../CONTRIBUTING.md) for what a rule proposal needs.

## Authorship

The rulebook does not decide who authored a map. `CART007` requires that source and authorship be *declared*; what goes there comes from the user, never from the plugin author by default. See [MAP_AUTHORSHIP_POLICY.md](MAP_AUTHORSHIP_POLICY.md).
