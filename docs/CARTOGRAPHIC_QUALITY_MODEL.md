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

An explicit rulebook of 28 rules across nine categories. Each rule carries:

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
| `elementos` | Title, legend, and whether the legend explains every visible layer |
| `escala` | Scale bar presence, proportion, unit validity for the CRS, numeric scale |
| `orientacao` | Orientation indicated, and by a symbol rather than a text label |
| `procedencia` | Source, authorship, reference system, production date |
| `grade` | Coordinate grid enabled, with a non-zero interval, annotated |
| `geometria` | Items inside the page and margins, no overlaps, map dominance |
| `tipografia` | Minimum printable font size, title/subtitle hierarchy |
| `projecao` | Projected CRS where metric measurement is claimed |
| `dados` | Extent contains the data, frame is not blank, output written |

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

## Testing the rules without QGIS

The rulebook evaluates an *observation* — a plain dictionary describing the layout — not a live QGIS object. `sigmai/cartography/inspector.py` produces observations from real layouts; `rulebook.py` never imports PyQGIS.

The practical consequence is that a rule can be tested in CI, and that a regression can be captured as data. `tests/test_cartographic_rulebook.py` contains the 0.1.1 map as an observation dictionary and asserts that it is rejected. If a future change makes the evaluator lenient again, that test fails.

It also means you can argue with a rule by reading a file. See [CONTRIBUTING.md](../CONTRIBUTING.md) for what a rule proposal needs.

## Authorship

The rulebook does not decide who authored a map. `CART007` requires that source and authorship be *declared*; what goes there comes from the user, never from the plugin author by default. See [MAP_AUTHORSHIP_POLICY.md](MAP_AUTHORSHIP_POLICY.md).
