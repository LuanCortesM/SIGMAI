# Map authorship policy

**MACIEL, L. S. C. is the author of the SIGMAI plugin. MACIEL, L. S. C. is not the author of the maps you make with it**, any more than the author of a word processor is the author of the documents written in it. This document is what backs that sentence in the README: where authorship comes from on a generated map, and where it does not.

## Where a map's credit line comes from

`compose_map` (the engine behind `sigmai_compose_map` and `sigmai_plan_map`) takes authorship as ordinary call parameters, on the same footing as the layers or the page size:

- `map_author` — who made this map. Written into the credit line as "Elaboração: …" (or the equivalent in `map_language`).
- `organization` — an affiliation line, if any.
- `data_source` — where the data came from. This is not optional in spirit: `CART007` in the [cartographic rulebook](CARTOGRAPHIC_QUALITY_MODEL.md) requires source and authorship to be declared on the map, on the reasoning that an unsourced map cannot be checked or cited.

None of these three default to the plugin author. If a call to `compose_map` omits them, the credit line simply does not carry a source or author line — it still carries `maptext(map_language, "credito_ferramenta")`, a neutral tool credit ("Produzido com SIGMAI/QGIS" in Portuguese, translated for the other fourteen languages `map_language` supports) that names the software, not a person. SIGMAI never inserts MACIEL, L. S. C.'s name into a generated map on your behalf.

## Setting it once instead of every call

A separate, small profile — `sigmai_run_command` with `get_user_profile` / `set_user_profile` / `clear_user_profile` — lets you store `default_map_author`, `default_map_author_email`, `default_organization` and `default_credit_line` locally, so you are not retyping them into every request in a session. It is stored under the same per-machine settings directory as the rest of SIGMAI's local state (`get_user_profile` reports the exact path), never uploaded anywhere. This profile is read by the classic `basic-map` / `professional-map` commands; the current `compose_map` engine always takes `map_author` / `organization` / `data_source` directly on the call, so an AI assistant composing a map for you should ask what to put there, or use what you already told it in the conversation, rather than assume a stored default applies.

## The one opt-in exception

The profile has one flag, `use_plugin_author_as_map_author_in_dev`, default `False`. Even when set, it only has an effect for the classic map commands, and only while the plugin's own Developer Mode is on — a convenience for testing the plugin itself, not a production default. It never applies to `compose_map`.

## Why this is worth a whole document

A plugin author's name ending up on a user's generated map — a dissertation figure, a report attached to someone else's name — is exactly the kind of overclaim this project spent its 0.2.x releases removing everywhere else. Authorship is a factual claim about who made a specific piece of work; getting it right by construction, rather than by convention the assistant might forget, is why this is a parameter on every call that produces a map rather than a setting anyone could leave on the plugin's own default.
