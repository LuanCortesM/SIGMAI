# Contributing to SIGMAI

Thanks for wanting to help. SIGMAI is a research product and a QGIS plugin; both roles shape how changes are reviewed.

## Getting support or reporting a problem

- **Something is broken** → open an issue with the *Bug report* template. The single most useful thing you can attach is the output of the panel's **Test connection** button plus the last lines of `sigmai/logs/sigmai.jsonl`. Redact nothing except the token — the logs never contain it.
- **A map came out wrong** → include the `audit` block returned by `compose_map`. It names the rules that failed and is usually enough to reproduce the case.
- **A question** → open a [Discussion](https://github.com/LuanCortesM/SIGMAI/discussions). Questions are welcome as issues too if you are not sure.

Expect a first reply within about a week. This is a single-maintainer project alongside a master's programme, so a fix may take longer than an answer.

## Setting up

```bash
git clone https://github.com/LuanCortesM/SIGMAI.git
cd SIGMAI
python -m pip install pytest
python -m pytest tests -q
```

The suite needs no QGIS. That is deliberate: `sigmai/cartography/pagespec.py`, `scaling.py`, `layoutgrid.py` and `rulebook.py` never import PyQGIS, so the cartographic decisions are verifiable in CI. Keep it that way — if a change to those modules needs QGIS to be tested, the logic is probably in the wrong module.

To test against a live QGIS, install the plugin from `tools/package_qgis_plugin_zip.py` and run the scripts in `tools/run_sigmai_*.py`.

## What a good change looks like

- **One concern per pull request.** A protocol fix and a layout change are two pull requests.
- **A test that fails before and passes after.** For a cartographic rule, that means an observation dictionary in `tests/test_cartographic_rulebook.py`; you do not need QGIS to write one.
- **Comments explain why, not what.** The code says what it does. A comment earns its place by recording a decision, a constraint, or a bug that a future reader would otherwise reintroduce.
- **Text in the interface goes in `sigmai/ui/strings.py`, in both languages.** Português do Brasil and English are both first-class.

## Proposing a cartographic rule

Rules are the contribution most likely to come from users, and they are cheap to add: a rule is a function plus an entry in `RULES`. A rule needs four things, and a pull request without them will be asked for them:

1. **What it checks**, expressed against the observation dictionary rather than a live layout.
2. **Why it exists** — the consequence for a reader of the map, in one sentence.
3. **A reference** — a standard, a textbook, the QGIS documentation. "It looks better" is not a rule.
4. **The fix** — the SIGMAI command that satisfies it, because that string is what the AI assistant reads and acts on.

Severity is `error` when the map is wrong, `warning` when it is defective but usable, `advice` when it could be better.

## Governance and releases

SIGMAI has a single maintainer, who reviews and merges every change and decides what goes into a release. Decisions are made in the open: a change starts as an issue or a Discussion, lands through a pull request with its test, and is recorded in [CHANGELOG.md](CHANGELOG.md). Contributors who send sustained, reviewed work can be invited as co-maintainers.

A release is cut only when the test suite passes, `tools/release_battery.py` reports `LIBERADO` and `tools/prepare_public_release.py` reports `PUBLIC_RELEASE_READY`. Each release is tagged (`vX.Y.Z`), published on the [QGIS plugin repository](https://plugins.qgis.org/plugins/sigmai/), and archived on Zenodo. Security problems should be reported privately by e-mail to the maintainer (herpetomantiqueira@gmail.com) rather than in a public issue.

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Licence

Contributions are accepted under the MIT License, matching the project.
