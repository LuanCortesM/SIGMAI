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

An explicit rulebook of 34 rules across ten categories. Each rule carries:

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
| `dados` | Extent contains the data, frame is not blank, the data occupy the frame, output written |
| `simbologia` | Layer colours remain distinguishable under simulated colour-vision deficiency |

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
- **`CART069` — the frame is occupied.** The frame is divided into a 3 × 3 grid; the polygon coverage of each cell is computed geometrically (up to 5 000 features per layer; larger layers fall back to the ink of the rendered PNG). A whole column or row with less than 5 % coverage (2 % ink) means the page shape does not match the data — a tall state on a landscape sheet — and the finding names the band ("west column", "south row"). Total coverage was tried first and rejected: a legitimate state map with a wide margin fails it, an empty band does not lie.
- **`CART070` — colours distinguishable by readers with a colour-vision deficiency.** The fill or stroke colour of each visible layer (and each class of a categorised or graduated renderer) is transformed with the protanopia, deuteranopia and tritanopia matrices of Machado, Oliveira & Fernandes (2009, *IEEE Transactions on Visualization and Computer Graphics* 15(6), severity 1.0) and compared pairwise in CIE L\*a\*b\*; a pair with ΔE\*ab below 15 under any of the three simulations is reported, with the Okabe & Ito (2008) palette offered as the fix.
- **`CART071` — fonts readable at the printed width.** When the composition was asked for as a journal figure (`journal_column`, `figure_width_mm`) or the audit is told `print_width_mm`, every font size is scaled by printed width ÷ page width and compared with the minimum readable size. A 7 pt caption on an A4 page becomes 3 pt in a single-column figure.

- **`CART072` — the legend fits its box.** `QgsLegendRenderer.minimumSize()` gives the size the legend content needs; when the item is not set to resize to contents and the content exceeds the box by more than 0.5 mm, QGIS clips the names at the edge and draws over whatever sits below, without any warning. `compose_map` measures the same thing and, before the audit, shrinks the legend font down to 6 pt and then drops the per-layer sources from the entries (they stay in the credit line and the recipe).

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
