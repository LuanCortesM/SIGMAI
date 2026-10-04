# Roadmap

What comes next, in the order it matters for the people SIGMAI is for. Proposals and discussion are welcome in [GitHub Discussions](https://github.com/LuanCortesM/SIGMAI/discussions).

## Evaluation with people

The rulebook's thresholds are declared design decisions, analysed for sensitivity but never measured with readers (see [experiments/2026-09-19_sensibilidade_limiares/](experiments/2026-09-19_sensibilidade_limiares/)), and every validation so far was run by the developer with an AI agent. Next:

- perceptual evaluation of the thresholds that decide grades (colour distance, scale-bar fraction, minimum printed font size) with real readers;
- blind evaluation of maps composed by SIGMAI and by other routes, by cartographers, with repeated requests and rounds;
- use by researchers without GIS training — the audience the plugin was designed for.

## Thematic cartography

The rulebook checks the form of a map, not its thematic content. Planned rules: classification of graduated layers, label hierarchy, information density.

## Map series

Atlas and map-series commands exist in the catalogue but are disabled until they meet the same standard as `compose_map` — composition, audit and recipe.

## Smaller items

- A rule for legend entries whose layer draws nothing inside the frame, so that layouts not composed by SIGMAI are audited for it too (the composer already leaves such layers out).

The history of earlier plans is in [archive/0.1/ROADMAP_0.2.md](archive/0.1/ROADMAP_0.2.md).
