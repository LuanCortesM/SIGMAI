---
title: 'SIGMAI: a consent-gated bridge that lets AI assistants compose and audit maps in QGIS'
tags:
  - Python
  - QGIS
  - cartography
  - Model Context Protocol
  - large language models
  - reproducible research
  - biodiversity
authors:
  - name: Luan da Silva Cortes Maciel
    orcid: 0000-0000-0000-0000  # TODO antes de submeter: o seu ORCID
    affiliation: 1
    corresponding: true
affiliations:
  - name: Escola Nacional de Botânica Tropical, Instituto de Pesquisas Jardim Botânico do Rio de Janeiro, Brazil
    index: 1
    ror: 033xtdz52
date: 4 October 2026
bibliography: paper.bib
---

# Summary

Most field studies in ecology and conservation need maps: where the study area is, where samples were collected, which protected areas are nearby. Producing a correct map involves decisions that are rarely part of a biologist's training, such as the coordinate reference system, the scale, the elements a map sheet must carry and where each data set came from. AI assistants can now write the code that drives a Geographic Information System (GIS), but to do so they need access to the user's computer, and they cannot tell whether the map they produced is right.

SIGMAI (Secure GIS-AI Interface) is a plugin for QGIS [@qgis] that sits between an AI assistant and the GIS. The assistant connects through the Model Context Protocol [@mcp_spec] and can only issue validated commands from a fixed catalogue; every command that changes the project or writes a file passes through a consent layer that the user controls. A cartographic engine composes complete map layouts from a short declarative request, and an explicit rulebook audits the exported map and tells the assistant, rule by rule, what is wrong and which command fixes it (\autoref{fig:map}). Each map carries a recipe that allows it to be reproduced and cited.

# Statement of need

Two problems motivated SIGMAI. The first is safety. An assistant that writes and runs PyQGIS code needs a terminal or a code-execution tool on the researcher's machine, and nothing between the request and its effect validates, limits or records what was done. The second is quality. Code that runs without error does not necessarily produce a correct map: in QGIS a coordinate grid can be enabled with a zero interval and draw nothing, a legend can list layers that are not in the frame, a scale bar can be labelled in the wrong unit, and the labelling engine can silently drop most labels. None of these raise an exception, so an assistant that cannot see the result reports success.

SIGMAI targets researchers who need correct, reproducible maps without being GIS specialists, and who increasingly delegate that work to AI assistants. It replaces arbitrary code execution with typed commands under the user's consent, and it replaces "the code ran" with an audit grounded in cartographic norms. Its rules rest on Brazil's national cartography regulations [@brasil1984decreto], cartography textbooks [@brewer2016maps; @slocum2009thematic], projection practice [@snyder1987projections] and a physiological model of colour-vision deficiency [@machado2009cvd]; every numeric threshold that is a design decision says so.

# State of the field

Research on AI-driven GIS has moved from code generation towards autonomous agents. @li2023autonomous proposed autonomous GIS, in which a large language model plans and writes spatial-analysis code; @li2025agenda set out a research agenda for it; and GIS Copilot [@akinboyewa2025copilot] brought the approach into QGIS as a plugin that generates and runs PyQGIS for spatial analysis. For maps specifically, MapGPT [@zhang2024mapgpt] lets a language model call cartographic tools, CartoAgent [@wang2025cartoagent] uses multimodal agents for style transfer and evaluation, and case studies with ChatGPT [@tao2023mapping; @pannoon2025choropleth] show that general-purpose assistants can produce maps but make errors in the code they generate.

Several open projects connect QGIS to assistants through the Model Context Protocol. QGISMCP [@santos_qgis_mcp] runs a socket server inside QGIS and includes a tool that executes arbitrary Python; qgis-mcp [@karasiak_qgis_mcp] exposes a large set of tools, including layout and rendering; QMCP [@mahmood_qmcp] runs the server inside QGIS and can render the map so the assistant can look at it.

SIGMAI differs from these in three ways. It has no code-execution path in normal operation: the assistant reaches QGIS only through allowlisted commands, gated by a consent layer with folder sandboxing, per-session limits, an audit trail and undo. Its composer derives page layout, extent, scale, scale bar, grid and projection from explicit numeric rules instead of leaving those decisions to the model. And its quality control is a machine-readable rulebook that measures the exported image, so that the assistant receives specific, actionable feedback rather than a picture it must interpret.

# Software design

SIGMAI has four parts. An MCP server, written against the Python standard library only, publishes 20 typed tools over JSON-RPC on standard input/output. It forwards each call to a bridge inside QGIS that accepts connections only on the loopback interface and requires a bearer token. The bridge validates the command against its schema, checks its permission level (read-only, safe write, plugin management, developer) and asks the consent layer; commands then run on the Qt main thread. Of 232 catalogued commands, 219 are enabled; the rest are refused as if they did not exist and listed with the reason, so the catalogue describes what the plugin does rather than what it might do.

The main trade-off is expressiveness against control. A code-execution tool lets an assistant do anything QGIS can do; a fixed vocabulary does less but can be validated, simulated with a dry run, logged, undone and explained to the user before it runs. SIGMAI chose the second, and keeps the first behind a developer mode that the user must enable by hand.

The cartographic engine is split so that its decisions can be verified without QGIS. Page geometry, scale selection, layout and the rulebook are pure Python; only the composer and the inspector touch the QGIS layout API. The composer fits the extent to the frame's aspect ratio before applying the margin, rounds the scale to the cartographic series, sizes the scale bar to a legible fraction of the frame, reprojects geographic data to the appropriate UTM zone (or to a national projection for large extents), picks page orientation and arrangement from the shape of the data, and styles layers with a palette that remains distinguishable under simulated dichromacy [@okabe2008cud; @machado2009cvd; @robertson1977cie]. The inspector turns a layout, including hand-made ones, into an observation dictionary; the rulebook evaluates 34 rules in ten categories against it and returns a grade, the failing rules, the reason each rule exists, its reference and the command that fixes it. Each composed map stores a recipe in the layout and in the exported PNG, with its parameters, the SHA-256 hash of every input file and the software versions; it can be read back, re-run with changes and turned into a Methods paragraph.

The test suite has 679 tests and runs on Linux, macOS and Windows with Python 3.9 and 3.12, plus a smoke test inside the official QGIS container. A release battery composes maps across every template, page size, orientation, format, data type and map language (683 checks), and a sensitivity analysis re-scores 138 maps while varying each threshold, to show which thresholds decide anything.

![A map composed by SIGMAI 1.1.3 from a one-call request (subject layer, context layer, inset, title, author and data source). The rulebook graded it A (95/100) with one warning, CART069: the eastern and southern bands of the frame contain no area data, because the neighbouring state's municipalities are not in the project. The warning names the bands and suggests adding that layer.\label{fig:map}](figure_carnaubas.png)

# Research impact statement

SIGMAI was developed as a research product of the author's master's programme in biodiversity in protected areas, to produce and audit the maps used in that work, and its first public release has been available from the official QGIS plugin repository since May 2026, where it was downloaded 382 times by October 2026. The first public version is archived on Zenodo [@maciel_sigmai_zenodo]. The repository documents the engineering experiments behind each release: in one, the same mapping request was given to an assistant using SIGMAI without access to the computer and to an assistant writing PyQGIS with full access; the first finished in 17–18 tool calls and 5.5 minutes, the second in 15 executions, 19 minutes and 12 API pitfalls solved by trial and error. Because the grade came from SIGMAI's own rulebook and the assistants were driven by the developer, this supports the difference in cost and traceability, not the cartographic superiority of either map.

<!-- TODO antes de submeter: a JOSS exige evidência de uso realizado, não intenção.
     Acrescentar aqui: (1) a dissertação defendida/depositada que usa os mapas do SIGMAI, com referência;
     (2) qualquer artigo ou preprint com figuras produzidas pelo SIGMAI;
     (3) grupos ou pessoas de fora que o usam (issues, e-mails, cursos), com o que for citável;
     (4) o número atualizado de downloads da versão corrente no repositório do QGIS. -->

# AI usage disclosure

Generative AI was used extensively in the development of SIGMAI. Anthropic's Claude models (Claude Opus 5, Claude Opus 5.5 and Claude Fable 5.1, used through Claude Code) wrote most of the source code, tests and documentation of versions 0.2 to 1.1.3 under the author's direction, helped diagnose failures found on real QGIS installations, and drafted this paper from the author's dissertation chapter. <!-- TODO: confirmar a lista; incluir outras ferramentas usadas (por exemplo, o OpenAI Codex nas versões 0.1, se for o caso) com versão e uso. --> The author defined the problem and the requirements from his own mapping practice; made the architectural decisions (no code-execution path, the consent layer, a deterministic composer, the rulebook as data); selected and checked every cartographic norm, threshold and reference against its source; designed the experiments; and reviewed, ran and validated the code on QGIS 3.40 and 4.0. The simulated assistant in the validation experiments belonged to the same model family that assisted development, so those experiments are engineering checks, not independent evaluations. The author takes full responsibility for the accuracy, originality and licensing of the software and of this paper.

# Acknowledgements

<!-- TODO antes de submeter: financiamento (bolsa, projeto) e agradecimentos. A JOSS exige declarar todo apoio financeiro; se não houve, escrever isso. -->

# References
