from __future__ import annotations

import ast
import configparser
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..security import normalize_output_path
from ..validators import ValidationError, require_param


PLUGIN_PACKAGE_EXCLUDES = {
    ".git",
    "__pycache__",
    "diagnostics",
    "test_outputs",
    ".pytest_cache",
    "logs",
}
PLUGIN_FILE_EXCLUDES = {".pyc", ".pyo", ".log", ".jsonl"}
ICON_EXTENSIONS = {".svg", ".png", ".ico", ".jpg", ".jpeg"}
SELF_NAMES = {"sigmai", "SIGMAI".lower(), "sigmai", "sigmai ai", "sigmai", "SIGMAI".lower()}
OFFICIAL_PLUGIN_REPOSITORY_URL = "https://plugins.qgis.org/plugins/plugins.xml"
OFFICIAL_PLUGIN_HOSTS = {"plugins.qgis.org"}
MAX_SAFE_REPOSITORY_XML_BYTES = 25_000_000


def _plugin_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        from qgis.core import QgsApplication  # type: ignore

        raw_path = QgsApplication.pluginPath()
        roots.extend(Path(path).resolve() for path in raw_path.split(os.pathsep) if path)
        settings_path = Path(QgsApplication.qgisSettingsDirPath()).resolve()
        roots.append(settings_path / "python" / "plugins")
        appdata = os.environ.get("APPDATA")
        if appdata:
            roots.append(Path(appdata) / "QGIS" / "QGIS3" / "profiles" / "default" / "python" / "plugins")
    except Exception:
        appdata = os.environ.get("APPDATA")
        if appdata:
            roots.append(Path(appdata) / "QGIS" / "QGIS3" / "profiles" / "default" / "python" / "plugins")
        current_plugin = Path(__file__).resolve().parents[1]
        if current_plugin.name != "sigmai":
            roots.append(current_plugin.parent)
    unique: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except Exception:
            resolved = root
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _find_plugin_path(plugin_name: str) -> Path | None:
    for root in _plugin_roots():
        candidate = (root / plugin_name).resolve()
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _current_plugin_path() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_self_plugin(plugin_name: str, plugin_path: Path | None = None) -> bool:
    normalized = plugin_name.strip().lower()
    if normalized in SELF_NAMES:
        return True
    if plugin_path is None:
        return False
    try:
        return plugin_path.resolve() == _current_plugin_path().resolve()
    except Exception:
        return False


def _read_metadata(path: Path) -> dict[str, str]:
    metadata_path = path / "metadata.txt"
    if not metadata_path.exists():
        return {}
    parser = configparser.ConfigParser()
    parser.read(metadata_path, encoding="utf-8")
    if not parser.has_section("general"):
        return {}
    return {key: value for key, value in parser.items("general")}


def _matches_plugin_provider(plugin_name: str, display_name: str, provider_id: str, provider_name: str) -> bool:
    needles = [plugin_name.strip().lower(), display_name.strip().lower()]
    needles = [needle for needle in needles if needle]
    haystacks = [provider_id.lower(), provider_name.lower()]
    return any(needle in haystack for needle in needles for haystack in haystacks)


def _metadata_errors(plugin_path: Path) -> tuple[bool, list[str], list[str], dict[str, str]]:
    metadata = _read_metadata(plugin_path)
    required = ["name", "description", "version", "qgisminimumversion", "author"]
    missing = [key for key in required if not metadata.get(key)]
    warnings = []
    if "experimental" not in metadata:
        warnings.append("metadata.txt does not declare experimental=True/False.")
    elif str(metadata.get("experimental", "")).strip().lower() == "true":
        warnings.append("metadata.txt declares experimental=True; public releases should use experimental=False.")
    return bool((plugin_path / "metadata.txt").exists() and not missing), missing, warnings, metadata


def _iter_files(plugin_path: Path) -> list[Path]:
    return [path for path in plugin_path.rglob("*") if path.is_file()]


def _relative_files(plugin_path: Path) -> list[str]:
    return [str(path.relative_to(plugin_path)).replace("\\", "/") for path in _iter_files(plugin_path)]


def _should_exclude(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in PLUGIN_PACKAGE_EXCLUDES for part in rel.parts):
        return True
    if path.suffix.lower() in PLUGIN_FILE_EXCLUDES:
        return True
    lowered = path.name.lower()
    return "token" in lowered or "current_bridge_session" in lowered


def _safe_output_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = _public_runtime_dir("outputs") / path
    return path.resolve()


def _public_runtime_dir(name: str) -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or str(Path.home())
    return Path(base) / "SIGMAI" / name


def _require_network_confirmation(params: dict[str, Any]) -> None:
    if not bool(params.get("confirm_network")):
        raise ValidationError("NETWORK_CONFIRMATION_REQUIRED", "QGIS plugin repository access requires confirm_network=true.", {})


def _safe_repository_url(raw_url: str | None = None, qgis_version: str | None = None) -> str:
    url = raw_url or OFFICIAL_PLUGIN_REPOSITORY_URL
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValidationError("PLUGIN_REPOSITORY_URL_BLOCKED", "Only HTTPS plugin repository URLs are allowed.", {"url": url})
    if parsed.hostname not in OFFICIAL_PLUGIN_HOSTS:
        raise ValidationError("PLUGIN_REPOSITORY_URL_BLOCKED", "Only the official QGIS plugin repository is enabled by default.", {"host": parsed.hostname})
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    if qgis_version and "qgis" not in query:
        query["qgis"] = qgis_version
    encoded = urllib.parse.urlencode(query)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, encoded, parsed.fragment))


def _safe_plugin_download_url(raw_url: str, repository_url: str = OFFICIAL_PLUGIN_REPOSITORY_URL) -> str:
    base = repository_url or OFFICIAL_PLUGIN_REPOSITORY_URL
    url = urllib.parse.urljoin(base, raw_url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_PLUGIN_HOSTS:
        raise ValidationError("PLUGIN_DOWNLOAD_URL_BLOCKED", "Only plugin ZIP downloads from the official QGIS plugin repository are allowed.", {"url": url, "host": parsed.hostname})
    if parsed.username or parsed.password:
        raise ValidationError("PLUGIN_DOWNLOAD_URL_BLOCKED", "Credentials in plugin download URLs are blocked.", {})
    return url


def _assert_official_https_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_PLUGIN_HOSTS:
        raise ValidationError("PLUGIN_NETWORK_URL_BLOCKED", "Only HTTPS requests to the official QGIS plugin repository are allowed.", {"url": url, "host": parsed.hostname})
    if parsed.username or parsed.password:
        raise ValidationError("PLUGIN_NETWORK_URL_BLOCKED", "Credentials in plugin repository URLs are blocked.", {})


def _fetch_url_bytes(url: str, timeout: int = 45, max_bytes: int = 120_000_000) -> bytes:
    _assert_official_https_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "SIGMAI/0.1 QGIS-plugin-manager"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - URL is restricted to HTTPS plugins.qgis.org by _assert_official_https_url.
            status = getattr(response, "status", 200)
            if int(status) >= 400:
                raise ValidationError("PLUGIN_REPOSITORY_HTTP_ERROR", "QGIS plugin repository returned an HTTP error.", {"url": url, "status": status})
            data = response.read(max_bytes + 1)
    except urllib.error.URLError as exc:
        raise ValidationError("PLUGIN_REPOSITORY_UNREACHABLE", "Could not reach the QGIS plugin repository.", {"url": url, "error": str(exc)}) from exc
    if len(data) > max_bytes:
        raise ValidationError("PLUGIN_DOWNLOAD_TOO_LARGE", "Plugin repository response exceeded the safe download limit.", {"url": url, "max_bytes": max_bytes})
    return data


def _safe_repository_xml_root(xml_bytes: bytes) -> ET.Element:
    if len(xml_bytes) > MAX_SAFE_REPOSITORY_XML_BYTES:
        raise ValidationError("PLUGIN_REPOSITORY_XML_TOO_LARGE", "Plugin repository XML exceeded the safe parsing limit.", {"max_bytes": MAX_SAFE_REPOSITORY_XML_BYTES})
    probe = xml_bytes[:4096].lower()
    if b"<!doctype" in probe or b"<!entity" in probe:
        raise ValidationError("PLUGIN_REPOSITORY_UNSAFE_XML", "Plugin repository XML with DTD or entity declarations is blocked.", {})
    return ET.fromstring(xml_bytes)  # nosec B314 - official repository XML is size-limited and DTD/entity declarations are rejected before parsing.


def _text_of(element: ET.Element, *names: str) -> str:
    for name in names:
        if element.get(name):
            return str(element.get(name) or "").strip()
        child = element.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _parse_repository_plugins(xml_bytes: bytes, repository_url: str) -> list[dict[str, Any]]:
    try:
        root = _safe_repository_xml_root(xml_bytes)
    except ET.ParseError as exc:
        raise ValidationError("PLUGIN_REPOSITORY_BAD_XML", "Plugin repository XML could not be parsed.", {"error": str(exc)}) from exc
    plugins: list[dict[str, Any]] = []
    for element in root.iter():
        if element.tag.lower().split("}")[-1] != "pyqgis_plugin":
            continue
        name = _text_of(element, "name") or _text_of(element, "plugin_name")
        package_name = _text_of(element, "module_name", "package_name", "plugin_id") or re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
        version = _text_of(element, "version")
        download_url = _text_of(element, "download_url", "file_name", "zip_repository")
        if download_url:
            download_url = _safe_plugin_download_url(download_url, repository_url)
        plugins.append(
            {
                "name": name,
                "package_name": package_name,
                "version": version,
                "description": _text_of(element, "description"),
                "author": _text_of(element, "author_name", "author"),
                "homepage": _text_of(element, "homepage"),
                "repository": _text_of(element, "repository"),
                "tracker": _text_of(element, "tracker"),
                "qgis_minimum_version": _text_of(element, "qgis_minimum_version", "qgisminimumversion"),
                "qgis_maximum_version": _text_of(element, "qgis_maximum_version", "qgismaximumversion"),
                "experimental": _text_of(element, "experimental"),
                "deprecated": _text_of(element, "deprecated"),
                "download_url": download_url,
            }
        )
    return plugins


def _select_repository_plugin(plugins: list[dict[str, Any]], plugin_name: str) -> dict[str, Any] | None:
    wanted = plugin_name.strip().lower()
    exact = [item for item in plugins if item.get("package_name", "").lower() == wanted or item.get("name", "").lower() == wanted]
    if exact:
        return exact[0]
    contains = [item for item in plugins if wanted in item.get("name", "").lower() or wanted in item.get("package_name", "").lower()]
    return contains[0] if contains else None


def _safe_extract_plugin_zip(zip_path: Path, target_root: Path) -> Path:
    target_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        members = archive.infolist()
        if not members:
            raise ValidationError("BAD_PLUGIN_ZIP", "Plugin ZIP is empty.", {"zip_path": str(zip_path)})
        roots = {Path(member.filename).parts[0] for member in members if member.filename and not member.filename.startswith(("/", "\\"))}
        for member in members:
            destination = (target_root / member.filename).resolve()
            if not str(destination).startswith(str(target_root.resolve())):
                raise ValidationError("BAD_PLUGIN_ZIP", "Plugin ZIP contains an unsafe path.", {"member": member.filename})
        archive.extractall(target_root)
    candidates = [target_root / root for root in roots if (target_root / root).is_dir() and (target_root / root / "metadata.txt").exists()]
    if not candidates and (target_root / "metadata.txt").exists():
        return target_root
    if len(candidates) != 1:
        raise ValidationError("BAD_PLUGIN_ZIP", "Plugin ZIP must contain exactly one plugin folder with metadata.txt.", {"candidates": [str(path) for path in candidates]})
    return candidates[0]


def _write_markdown_report(path: Path, title: str, data: dict[str, Any], confirm_overwrite: bool) -> None:
    if path.exists() and not confirm_overwrite:
        raise ValidationError("OUTPUT_EXISTS", "Output path exists. Pass confirm_overwrite=true to replace it.", {"path": str(path)})
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", "", f"Generated at: `{datetime.now().isoformat(timespec='seconds')}`", ""]
    for key, value in data.items():
        lines.append(f"## {key.replace('_', ' ').title()}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(value, indent=2, ensure_ascii=False, default=str))
        lines.append("```")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _copy_tree_safe(source: Path, target: Path) -> list[str]:
    copied: list[str] = []
    target.mkdir(parents=True, exist_ok=True)
    for item in source.rglob("*"):
        if item.is_dir() or _should_exclude(item, source):
            continue
        rel = item.relative_to(source)
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        copied.append(str(rel).replace("\\", "/"))
    return copied


def _backup_plugin(plugin_path: Path, name: str) -> Path:
    base = _public_runtime_dir("backups")
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = base / f"{name}_backup_{stamp}.zip"
    _zip_plugin(plugin_path, backup_path)
    return backup_path


def _zip_plugin(plugin_path: Path, output_path: Path) -> list[str]:
    manifest: list[str] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in _iter_files(plugin_path):
            if _should_exclude(item, plugin_path):
                continue
            rel = item.relative_to(plugin_path)
            archive_name = str(Path(plugin_path.name) / rel).replace("\\", "/")
            archive.write(item, archive_name)
            manifest.append(archive_name)
    return manifest


def _plugin_summary(plugin_name: str, plugin_path: Path) -> dict[str, Any]:
    metadata = _read_metadata(plugin_path)
    files = _relative_files(plugin_path)
    py_files = [file for file in files if file.lower().endswith(".py")]
    lower_files = [file.lower() for file in files]
    return {
        "plugin_name": plugin_name,
        "path": str(plugin_path),
        "metadata_exists": bool(metadata),
        "init_exists": (plugin_path / "__init__.py").exists(),
        "has_icon": any(Path(file).suffix.lower() in ICON_EXTENSIONS and "icon" in file.lower() for file in files),
        "has_processing_provider": any("provider" in file.lower() for file in files),
        "has_ui_files": any(file.endswith((".ui", ".qrc", ".qml", ".svg")) for file in lower_files),
        "has_resources": any(file.endswith((".qrc", ".rc", ".svg", ".png", ".qml")) for file in lower_files),
        "python_file_count": len(py_files),
        "static_entrypoints": _static_plugin_entrypoints(plugin_path, py_files),
        "static_risk": _static_plugin_risk(plugin_path, py_files),
        "detected_files": files[:500],
        "metadata": metadata,
    }


def _read_limited_text(path: Path, max_chars: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def _static_plugin_entrypoints(plugin_path: Path, py_files: list[str]) -> dict[str, Any]:
    tokens = {
        "class_factory": False,
        "init_gui": False,
        "processing_provider": False,
        "menu_actions": False,
        "toolbar_actions": False,
        "dock_widgets": False,
        "dialogs": False,
    }
    action_texts: list[str] = []
    for rel in py_files[:250]:
        text = _read_limited_text(plugin_path / rel)
        lower = text.lower()
        tokens["class_factory"] = tokens["class_factory"] or "classfactory" in lower
        tokens["init_gui"] = tokens["init_gui"] or "def initgui" in lower
        tokens["processing_provider"] = tokens["processing_provider"] or "qgsprocessingprovider" in lower or "processingprovider" in lower
        tokens["menu_actions"] = tokens["menu_actions"] or "addplugintomenu" in lower or "addpluginmenu" in lower
        tokens["toolbar_actions"] = tokens["toolbar_actions"] or "addtoolbaricon" in lower or "addtoolbar" in lower
        tokens["dock_widgets"] = tokens["dock_widgets"] or "qdockwidget" in lower
        tokens["dialogs"] = tokens["dialogs"] or "qdialog" in lower or ".ui" in lower
        if "qaction" in lower:
            for match in re.finditer(r"QAction\s*\(\s*(?:QIcon\([^)]*\)\s*,\s*)?['\"]([^'\"]{1,80})['\"]", text):
                action_texts.append(match.group(1))
    return {**tokens, "detected_action_labels": sorted(set(action_texts))[:50]}


def _static_plugin_risk(plugin_path: Path, py_files: list[str]) -> dict[str, Any]:
    categories: set[str] = set()
    findings: list[str] = []
    for rel in py_files[:250]:
        text = _read_limited_text(plugin_path / rel)
        lower = text.lower()
        if any(term in lower for term in ["urllib", "requests.", "qgsnetworkaccessmanager", "overpass", "http://", "https://"]):
            categories.add("network_access")
            findings.append(f"{rel}: network access markers")
        if any(term in lower for term in ["subprocess", "os.system", "popen(", "eval(", "exec("]):
            categories.add("arbitrary_process_or_code_risk")
            findings.append(f"{rel}: process/code execution markers")
        if any(term in lower for term in ["deletefeature", "deletefeatures", "truncate", "drop table", "startediting", "commit changes"]):
            categories.add("data_mutation")
            findings.append(f"{rel}: data mutation markers")
        if any(term in lower for term in ["qgsprocessingprovider", "processingprovider"]):
            categories.add("processing_provider")
        if any(term in lower for term in ["authcfg", "password", "token", "secret"]):
            categories.add("credential_sensitive")
            findings.append(f"{rel}: credential markers")
    if "arbitrary_process_or_code_risk" in categories or "credential_sensitive" in categories:
        risk_level = "high"
    elif "data_mutation" in categories or "network_access" in categories:
        risk_level = "medium"
    else:
        risk_level = "low"
    return {
        "risk_level": risk_level,
        "categories": sorted(categories) or ["static_inspection_only"],
        "findings": findings[:80],
        "safe_generic_modes": [
            "inspect_metadata",
            "inspect_static_entrypoints",
            "inspect_processing_algorithms",
            "dry_run_processing_algorithm",
        ],
        "blocked_modes": [
            "arbitrary_python_call",
            "direct_ui_action_invocation",
            "unconfirmed_network_or_data_mutation",
        ],
    }


def _require_plugin(plugin_name: str) -> Path:
    plugin_path = _find_plugin_path(plugin_name)
    if plugin_path is None:
        raise ValidationError("PLUGIN_NOT_FOUND", "Plugin was not found in known plugin folders.", {"plugin_name": plugin_name})
    return plugin_path


def list_installed_plugins(params: dict[str, Any], context: dict[str, Any]):
    discovered: dict[str, dict[str, Any]] = {}
    for root in _plugin_roots():
        if not root.exists():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            metadata = _read_metadata(child)
            discovered[child.name] = {
                "name": child.name,
                "path": str(child),
                "metadata_exists": bool(metadata),
                "display_name": metadata.get("name", child.name),
                "version": metadata.get("version", ""),
            }
    try:
        import qgis.utils  # type: ignore

        active = set(getattr(qgis.utils, "active_plugins", []))
        loaded = set(getattr(qgis.utils, "plugins", {}).keys())
        for name, item in discovered.items():
            item["active"] = name in active
            item["loaded"] = name in loaded
    except Exception:
        for item in discovered.values():
            item["active"] = False
            item["loaded"] = False
    return {"plugins": sorted(discovered.values(), key=lambda item: item["name"].lower()), "plugin_roots": [str(root) for root in _plugin_roots()]}


def list_qgis_plugins_extended(params: dict[str, Any], context: dict[str, Any]):
    base = list_installed_plugins(params, context)
    plugins = []
    for item in base["plugins"]:
        plugin_name = item["name"]
        plugin_path = Path(item["path"])
        metadata = _read_metadata(plugin_path)
        has_provider = any("provider" in rel.lower() for rel in _relative_files(plugin_path)[:1000])
        algorithms = []
        try:
            from qgis.core import QgsApplication  # type: ignore

            registry = QgsApplication.processingRegistry()
            display_name = metadata.get("name", "")
            for provider in registry.providers():
                if _matches_plugin_provider(plugin_name, display_name, provider.id(), provider.name()):
                    algorithms.extend([algorithm.id() for algorithm in provider.algorithms()])
        except Exception:
            pass
        risk_level = "medium" if has_provider else "low"
        if plugin_name.lower() in {"sigmai", "sigmai"}:
            risk_level = "self_management_required"
        plugins.append(
            {
                **item,
                "package": plugin_name,
                "category": metadata.get("category", ""),
                "author": metadata.get("author", ""),
                "has_processing_provider": has_provider or bool(algorithms),
                "algorithms_exposed": sorted(algorithms),
                "safe_to_call": bool(algorithms),
                "risk_level": risk_level,
                "metadata": metadata,
            }
        )
    return {"plugins": plugins, "plugin_roots": base["plugin_roots"]}


def inspect_plugin_capabilities(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _require_plugin(plugin_name)
    summary = _plugin_summary(plugin_name, plugin_path)
    summary["runtime"] = check_plugin_runtime_status({"plugin_name": plugin_name}, context)
    summary["processing_provider"] = check_processing_provider_registration({"plugin_name": plugin_name}, context)
    summary["risk_level"] = "self_management_required" if _is_self_plugin(plugin_name, plugin_path) else ("medium" if summary.get("has_processing_provider") else "low")
    summary["safe_usage_note"] = "Prefer Processing provider algorithms through SIGMAI allowlist/adapters. Do not execute arbitrary plugin Python."
    return summary


def list_plugin_processing_algorithms(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str).lower()
    algorithms = []
    try:
        from qgis.core import QgsApplication  # type: ignore

        metadata = _read_metadata(_find_plugin_path(plugin_name) or Path())
        display_name = metadata.get("name", "")
        for provider in QgsApplication.processingRegistry().providers():
            if _matches_plugin_provider(plugin_name, display_name, provider.id(), provider.name()):
                algorithms.extend({"id": alg.id(), "name": alg.displayName(), "provider": provider.id()} for alg in provider.algorithms())
    except Exception:
        pass
    return {"plugin_name": plugin_name, "algorithms": sorted(algorithms, key=lambda item: item["id"])}


def _algorithm_parameter_manifest(algorithm: Any) -> list[dict[str, Any]]:
    parameters = []
    for definition in algorithm.parameterDefinitions():
        optional = _processing_parameter_is_optional(definition)
        parameters.append(
            {
                "name": definition.name(),
                "description": definition.description(),
                "type": definition.type(),
                "optional": optional,
                "default_value": str(definition.defaultValue()) if definition.defaultValue() is not None else None,
            }
        )
    return parameters


def _processing_parameter_is_optional(definition: Any) -> bool:
    try:
        from qgis.core import QgsProcessingParameterDefinition  # type: ignore

        return bool(definition.flags() & QgsProcessingParameterDefinition.FlagOptional)
    except Exception:
        try:
            flags = int(definition.flags()) if hasattr(definition, "flags") else 0
            return bool(flags & 2)
        except Exception:
            return False


def _algorithm_output_manifest(algorithm: Any) -> list[dict[str, Any]]:
    outputs = []
    for definition in algorithm.outputDefinitions():
        outputs.append({"name": definition.name(), "description": definition.description(), "type": definition.type()})
    return outputs


def _find_processing_algorithm(algorithm_id: str):
    try:
        from qgis.core import QgsApplication  # type: ignore

        return QgsApplication.processingRegistry().algorithmById(algorithm_id)
    except Exception:
        return None


def _classify_algorithm_risk(algorithm_id: str, parameters: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> dict[str, Any]:
    provider = algorithm_id.split(":", 1)[0].lower() if ":" in algorithm_id else ""
    joined = " ".join([algorithm_id.lower(), *[item.get("name", "").lower() for item in parameters], *[item.get("description", "").lower() for item in parameters]])
    categories = []
    required_confirmations = []
    blockers = []
    if provider in {"quickosm"} or any(term in joined for term in ["server", "url", "overpass", "download", "network", "wfs", "wms", "http"]):
        categories.append("network_read")
        required_confirmations.append("confirm_network")
    if outputs or any("output" in item.get("name", "").lower() for item in parameters):
        categories.append("creates_new_output")
    if any(term in joined for term in ["delete", "remove", "drop", "overwrite", "edit", "update existing"]):
        categories.append("possible_data_mutation")
        required_confirmations.append("confirm_destructive")
        blockers.append("Manual review required before modifying existing data.")
    if provider in {"qgis2web"} or any(term in joined for term in ["export project", "webmap", "html", "leaflet", "openlayers"]):
        categories.append("project_export")
    if any(term in joined for term in ["password", "credential", "authcfg", "token", "secret"]):
        categories.append("credential_sensitive")
        blockers.append("Credential-sensitive algorithms need a dedicated adapter.")
    if not categories:
        categories.append("safe_read_only")
    if "possible_data_mutation" in categories or "credential_sensitive" in categories:
        risk_level = "high"
    elif "network_read" in categories or "project_export" in categories:
        risk_level = "medium"
    elif "creates_new_output" in categories:
        risk_level = "low"
    else:
        risk_level = "low"
    generic_execution = "dry_run_only"
    if risk_level == "low":
        generic_execution = "safe_with_validated_outputs"
    if risk_level == "medium":
        generic_execution = "requires_explicit_confirmation"
    return {
        "risk_level": risk_level,
        "risk_categories": sorted(set(categories)),
        "required_confirmations": sorted(set(required_confirmations)),
        "generic_execution": generic_execution,
        "blockers": blockers,
    }


def _algorithm_manifest(algorithm_id: str) -> dict[str, Any]:
    algorithm = _find_processing_algorithm(algorithm_id)
    if algorithm is None:
        return {"id": algorithm_id, "found": False, "risk": {"risk_level": "unknown", "blockers": ["Algorithm not found in current Processing registry."]}}
    parameters = _algorithm_parameter_manifest(algorithm)
    outputs = _algorithm_output_manifest(algorithm)
    provider = algorithm.provider().id() if algorithm.provider() else algorithm_id.split(":", 1)[0]
    risk = _classify_algorithm_risk(algorithm_id, parameters, outputs)
    return {
        "id": algorithm.id(),
        "name": algorithm.displayName(),
        "group": algorithm.group(),
        "provider": provider,
        "found": True,
        "parameters": parameters,
        "outputs": outputs,
        "risk": risk,
    }


def build_plugin_capability_manifest(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = str(params.get("plugin_name") or "").strip()
    max_algorithms = max(1, min(int(params.get("max_algorithms", 100)), 500))
    if plugin_name:
        plugin_names = [plugin_name]
    else:
        inventory = list_qgis_plugins_extended(params, context)
        include_inactive = bool(params.get("include_inactive", True))
        plugin_names = [
            item["package"]
            for item in inventory.get("plugins", [])
            if include_inactive or item.get("active") or item.get("loaded") or item.get("has_processing_provider")
        ]
    manifests = []
    for name in plugin_names:
        try:
            capabilities = inspect_plugin_capabilities({"plugin_name": name}, context)
            algorithm_refs = list_plugin_processing_algorithms({"plugin_name": name}, context).get("algorithms", [])
            algorithms = [_algorithm_manifest(item["id"]) for item in algorithm_refs[:max_algorithms]]
            manifests.append(
                {
                    "plugin_name": name,
                    "display_name": capabilities.get("metadata", {}).get("name", name),
                    "path": capabilities.get("path", ""),
                    "version": capabilities.get("metadata", {}).get("version", ""),
                    "runtime": capabilities.get("runtime", {}),
                    "processing_provider": capabilities.get("processing_provider", {}),
                    "static_entrypoints": capabilities.get("static_entrypoints", {}),
                    "static_risk": capabilities.get("static_risk", {}),
                    "algorithm_count": len(algorithm_refs),
                    "algorithms": algorithms,
                    "safe_usage_policy": {
                        "inspectable": True,
                        "direct_python_invocation": False,
                        "ui_action_invocation": False,
                        "generic_processing_execution": "Allowed only when the algorithm is found in Processing, risk classification permits it, required confirmations are present and output paths are validated.",
                        "dedicated_adapter_recommended_when": [
                            "plugin exposes only UI actions",
                            "algorithm touches credentials",
                            "algorithm mutates existing data",
                            "algorithm has complex side effects",
                        ],
                    },
                }
            )
        except Exception as exc:
            manifests.append({"plugin_name": name, "error": str(exc), "algorithm_count": 0, "algorithms": []})
    return {
        "schema_version": "1.0",
        "manifest_type": "generic_qgis_plugin_capability_manifest",
        "plugins": manifests,
        "plugin_count": len(manifests),
        "algorithm_count": sum(item.get("algorithm_count", 0) for item in manifests),
    }


def dry_run_plugin_algorithm_generic(params: dict[str, Any], context: dict[str, Any]):
    algorithm_id = require_param(params, "algorithm_id", str)
    provided_parameters = params.get("parameters", {})
    if not isinstance(provided_parameters, dict):
        raise ValidationError("BAD_REQUEST", "parameters must be a JSON object.", {"algorithm_id": algorithm_id})
    manifest = _algorithm_manifest(algorithm_id)
    if not manifest.get("found"):
        raise ValidationError("PLUGIN_ALGORITHM_NOT_FOUND", "Plugin Processing algorithm was not found.", {"algorithm_id": algorithm_id})
    missing_required = [
        item["name"]
        for item in manifest.get("parameters", [])
        if not item.get("optional") and item.get("default_value") in (None, "") and item["name"] not in provided_parameters
    ]
    output_parameters = [
        item["name"]
        for item in manifest.get("parameters", [])
        if "output" in item.get("name", "").lower() and item["name"] in provided_parameters
    ]
    return {
        "dry_run": True,
        "algorithm": manifest,
        "provided_parameters": provided_parameters,
        "missing_required_parameters": missing_required,
        "output_parameters": output_parameters,
        "can_attempt_generic_run": not missing_required and manifest.get("risk", {}).get("generic_execution") != "dry_run_only",
        "execution_policy": manifest.get("risk", {}),
        "changes": ["No plugin algorithm was executed. This command only builds a safe execution plan."],
    }


def run_plugin_algorithm_generic_safe(params: dict[str, Any], context: dict[str, Any]):
    plan = dry_run_plugin_algorithm_generic(params, context)
    if context.get("dry_run") or bool(params.get("dry_run_only", False)):
        return plan
    risk = plan["execution_policy"]
    if plan["missing_required_parameters"]:
        raise ValidationError("PLUGIN_PARAMETERS_MISSING", "Required Processing parameters are missing.", {"missing": plan["missing_required_parameters"]})
    if risk.get("risk_level") not in {"low"}:
        if "confirm_generic_plugin_run" not in params:
            raise ValidationError(
                "GENERIC_PLUGIN_RUN_CONFIRMATION_REQUIRED",
                "Medium/high-risk plugin algorithms require confirm_generic_plugin_run=true and any risk-specific confirmations.",
                {"risk": risk},
            )
    if "confirm_network" in risk.get("required_confirmations", []) and not bool(params.get("confirm_network")):
        raise ValidationError("NETWORK_CONFIRMATION_REQUIRED", "This plugin algorithm may use network access and requires confirm_network=true.", {"algorithm_id": params.get("algorithm_id")})
    if risk.get("blockers"):
        raise ValidationError("GENERIC_PLUGIN_RUN_BLOCKED", "This plugin algorithm needs a dedicated adapter before real execution.", {"risk": risk})
    for key, value in params.get("parameters", {}).items():
        if "output" not in key.lower() or not isinstance(value, str) or value == "TEMPORARY_OUTPUT":
            continue
        output_path = normalize_output_path(value)
        if output_path.exists() and not bool(params.get("confirm_overwrite", False)):
            raise ValidationError("OVERWRITE_BLOCKED", "Output path exists. Pass confirm_overwrite=true to replace it.", {"path": str(output_path)})
        if output_path.parent and not output_path.parent.exists():
            raise ValidationError("BAD_REQUEST", "Output directory does not exist.", {"path": str(output_path.parent)})
    try:
        import processing  # type: ignore
    except Exception as exc:
        raise ValidationError("PROCESSING_NOT_AVAILABLE", "QGIS Processing is not available.", {}) from exc
    result = processing.run(params["algorithm_id"], params.get("parameters", {}))
    return {"algorithm": params["algorithm_id"], "result": {key: str(value) for key, value in result.items()}, "generic_plugin_run": True, "risk": risk}


def get_plugin_algorithm_info(params: dict[str, Any], context: dict[str, Any]):
    from .processing_inventory import get_processing_algorithm_info

    return get_processing_algorithm_info({"algorithm_id": require_param(params, "algorithm_id", str)}, context)


def run_plugin_algorithm_safe(params: dict[str, Any], context: dict[str, Any]):
    from .run_processing import handle

    algorithm_id = require_param(params, "algorithm_id", str)
    allowed_plugin_algorithms = {"topotrail:topotrail"}
    if algorithm_id not in allowed_plugin_algorithms:
        raise ValidationError("PLUGIN_ALGORITHM_NOT_ALLOWED", "Plugin algorithm is not allowlisted for safe execution.", {"algorithm_id": algorithm_id, "allowed": sorted(allowed_plugin_algorithms)})
    return handle({"algorithm": algorithm_id, "parameters": params.get("parameters", {}), "confirm_overwrite": bool(params.get("confirm_overwrite", False))}, context)


def generate_plugin_adapter_report(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    capabilities = inspect_plugin_capabilities({"plugin_name": plugin_name}, context)
    algorithms = list_plugin_processing_algorithms({"plugin_name": plugin_name}, context)
    payload = {"plugin_name": plugin_name, "capabilities": capabilities, "algorithms": algorithms, "recommendations": ["Expose only documented Processing algorithms through explicit SIGMAI wrappers or allowlisted plugin adapters."]}
    output_path_value = params.get("output_path")
    if output_path_value:
        output_path = normalize_output_path(str(output_path_value))
        if context.get("dry_run"):
            return {**payload, "dry_run": True, "would_write": str(output_path)}
        _write_markdown_report(output_path, f"SIGMAI Plugin Adapter Report - {plugin_name}", payload, bool(params.get("confirm_overwrite", False)))
        payload["output_path"] = str(output_path)
    return payload


def search_qgis_plugin_repository(params: dict[str, Any], context: dict[str, Any]):
    _require_network_confirmation(params)
    query = str(params.get("query", "")).strip().lower()
    qgis_version = str(params.get("qgis_version", "") or "").strip()
    repository_url = _safe_repository_url(str(params.get("repository_url") or OFFICIAL_PLUGIN_REPOSITORY_URL), qgis_version=qgis_version)
    xml_bytes = _fetch_url_bytes(repository_url)
    plugins = _parse_repository_plugins(xml_bytes, repository_url)
    if query:
        plugins = [
            item
            for item in plugins
            if any(
                query in text
                for text in (
                    item.get("name", "").lower(),
                    item.get("package_name", "").lower(),
                    item.get("description", "").lower(),
                )
            )
        ]
    limit = max(1, min(int(params.get("limit", 20)), 100))
    return {
        "repository_url": repository_url,
        "query": query,
        "count": len(plugins),
        "plugins": plugins[:limit],
        "network_request_made": True,
        "official_repository_only": True,
    }


def download_qgis_plugin_zip(params: dict[str, Any], context: dict[str, Any]):
    _require_network_confirmation(params)
    repository_url = _safe_repository_url(str(params.get("repository_url") or OFFICIAL_PLUGIN_REPOSITORY_URL), qgis_version=str(params.get("qgis_version", "") or ""))
    download_url = str(params.get("download_url") or "").strip()
    plugin_name = str(params.get("plugin_name") or "").strip()
    selected: dict[str, Any] | None = None
    if not download_url:
        if not plugin_name:
            raise ValidationError("BAD_REQUEST", "Provide plugin_name or download_url.", {})
        plugins = _parse_repository_plugins(_fetch_url_bytes(repository_url), repository_url)
        selected = _select_repository_plugin(plugins, plugin_name)
        if not selected:
            raise ValidationError("PLUGIN_NOT_FOUND", "Plugin was not found in the QGIS repository.", {"plugin_name": plugin_name})
        download_url = str(selected.get("download_url") or "")
    download_url = _safe_plugin_download_url(download_url, repository_url)
    output_path = _safe_output_path(str(params.get("output_path") or Path.cwd() / "test_outputs" / "qgis_plugins" / Path(urllib.parse.urlparse(download_url).path).name))
    if output_path.suffix.lower() != ".zip":
        output_path = output_path.with_suffix(".zip")
    if output_path.exists() and not bool(params.get("confirm_overwrite")):
        raise ValidationError("OUTPUT_EXISTS", "Plugin ZIP output exists. Pass confirm_overwrite=true to replace it.", {"output_path": str(output_path)})
    if context.get("dry_run"):
        return {"dry_run": True, "plugin": selected, "download_url": download_url, "output_path": str(output_path), "network_request_made": False}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = _fetch_url_bytes(download_url, max_bytes=int(params.get("max_bytes", 120_000_000)))
    output_path.write_bytes(data)
    if not zipfile.is_zipfile(output_path):
        output_path.unlink(missing_ok=True)
        raise ValidationError("BAD_PLUGIN_ZIP", "Downloaded file is not a valid ZIP.", {"download_url": download_url})
    return {"plugin": selected, "download_url": download_url, "output_path": str(output_path), "size": output_path.stat().st_size}


def inspect_qgis_plugin_zip(params: dict[str, Any], context: dict[str, Any]):
    zip_path = _safe_output_path(require_param(params, "zip_path", str))
    if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
        raise ValidationError("BAD_PLUGIN_ZIP", "Plugin ZIP was not found or is not a valid ZIP.", {"zip_path": str(zip_path)})
    with tempfile.TemporaryDirectory(prefix="sigmai_plugin_zip_") as tmp:
        plugin_folder = _safe_extract_plugin_zip(zip_path, Path(tmp))
        valid, missing, warnings, metadata = _metadata_errors(plugin_folder)
        manifest = [str(path.relative_to(plugin_folder)).replace("\\", "/") for path in _iter_files(plugin_folder)[:500]]
    return {"zip_path": str(zip_path), "metadata_valid": valid, "missing_metadata_fields": missing, "warnings": warnings, "metadata": metadata, "manifest_sample": manifest}


def install_plugin_from_zip(params: dict[str, Any], context: dict[str, Any]):
    zip_path = _safe_output_path(require_param(params, "zip_path", str))
    if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
        raise ValidationError("BAD_PLUGIN_ZIP", "Plugin ZIP was not found or is not a valid ZIP.", {"zip_path": str(zip_path)})
    with tempfile.TemporaryDirectory(prefix="sigmai_plugin_install_") as tmp:
        plugin_folder = _safe_extract_plugin_zip(zip_path, Path(tmp))
        plugin_name = str(params.get("plugin_name") or plugin_folder.name)
        install_params = {"source_folder": str(plugin_folder), "plugin_name": plugin_name}
        return _install_or_update_from_folder(install_params, context, update=bool(params.get("update", False)))


def install_qgis_plugin_from_repository(params: dict[str, Any], context: dict[str, Any]):
    _require_network_confirmation(params)
    plugin_name = require_param(params, "plugin_name", str)
    if context.get("dry_run"):
        search = search_qgis_plugin_repository({**params, "query": plugin_name, "limit": 5}, {**context, "dry_run": False})
        selected = _select_repository_plugin(search.get("plugins", []), plugin_name)
        return {"dry_run": True, "plugin": selected, "would_download": bool(selected and selected.get("download_url")), "would_install": bool(selected), "restart_required": True}
    with tempfile.TemporaryDirectory(prefix="sigmai_plugin_repo_") as tmp:
        zip_path = Path(tmp) / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', plugin_name)}.zip"
        downloaded = download_qgis_plugin_zip({**params, "output_path": str(zip_path), "confirm_overwrite": True}, context)
        install_params = {"zip_path": downloaded["output_path"], "update": bool(params.get("update", False))}
        if params.get("target_plugin_name"):
            install_params["plugin_name"] = str(params["target_plugin_name"])
        installed = install_plugin_from_zip(install_params, context)
    return {"download": downloaded, "install": installed, "restart_required": True}


def inspect_plugin(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _require_plugin(plugin_name)
    data = _plugin_summary(plugin_name, plugin_path)
    warnings = []
    recommendations = []
    if not data["metadata_exists"]:
        warnings.append("metadata.txt missing or invalid.")
    if not data["init_exists"]:
        warnings.append("__init__.py missing.")
    if not data["has_icon"]:
        recommendations.append("Add a plugin icon for QGIS Plugin Repository polish.")
    data["warnings"] = warnings
    data["recommendations"] = recommendations
    data["is_self"] = _is_self_plugin(plugin_name, plugin_path)
    return data


def validate_metadata_txt(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _require_plugin(plugin_name)
    valid, missing, warnings, metadata = _metadata_errors(plugin_path)
    return {
        "plugin_name": plugin_name,
        "metadata_path": str(plugin_path / "metadata.txt"),
        "valid": valid,
        "missing_required_fields": missing,
        "warnings": warnings,
        "metadata": metadata,
    }


def check_plugin_structure(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _require_plugin(plugin_name)
    files = _relative_files(plugin_path)
    checks = {
        "metadata_txt": (plugin_path / "metadata.txt").exists(),
        "init_py": (plugin_path / "__init__.py").exists(),
        "plugin_py": (plugin_path / "plugin.py").exists(),
        "resources_py": (plugin_path / "resources.py").exists(),
        "icons_dir": (plugin_path / "icons").exists(),
        "i18n_dir": (plugin_path / "i18n").exists(),
        "processing_dir": (plugin_path / "processing").exists(),
        "readme": any(Path(file).name.lower().startswith("readme") for file in files),
        "license": any(Path(file).name.lower().startswith("license") for file in files),
    }
    packaging_issues = [file for file in files if "__pycache__" in file or file.endswith((".pyc", ".pyo")) or file.startswith(("diagnostics/", "test_outputs/"))]
    warnings = []
    if not checks["metadata_txt"]:
        warnings.append("metadata.txt is required.")
    if not checks["init_py"]:
        warnings.append("__init__.py is required.")
    if not checks["plugin_py"]:
        warnings.append("plugin.py was not found. This may be valid only if __init__.py points to another module.")
    if packaging_issues:
        warnings.append("Package contains generated/local files that should be excluded.")
    return {"plugin_name": plugin_name, "path": str(plugin_path), "checks": checks, "packaging_issues": packaging_issues, "warnings": warnings, "valid": checks["metadata_txt"] and checks["init_py"] and not packaging_issues}


def check_plugin_imports(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _require_plugin(plugin_name)
    files = sorted(path for path in plugin_path.rglob("*.py") if "__pycache__" not in path.parts)
    imports: list[dict[str, Any]] = []
    syntax_errors: list[dict[str, Any]] = []
    for path in files:
        rel = str(path.relative_to(plugin_path)).replace("\\", "/")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            syntax_errors.append({"file": rel, "line": exc.lineno, "message": exc.msg})
            continue
        except UnicodeDecodeError as exc:
            syntax_errors.append({"file": rel, "line": None, "message": f"Could not decode file: {exc}"})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"file": rel, "module": alias.name, "kind": "import", "line": node.lineno})
            elif isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                imports.append({"file": rel, "module": module, "kind": "from", "line": node.lineno, "relative": node.level > 0})
    qgis_imports = sorted({item["module"] for item in imports if str(item["module"]).startswith("qgis")})
    pyqt_imports = sorted({item["module"] for item in imports if "PyQt" in str(item["module"])})
    relative_imports = [item for item in imports if item.get("relative")]
    builtin_or_common = {"os", "sys", "json", "typing", "pathlib", "datetime", "time", "zipfile", "shutil", "configparser", "ast", "subprocess", "urllib", "http", "threading", "secrets", "uuid"}
    external_candidates = sorted({str(item["module"]).split(".")[0].lstrip(".") for item in imports if str(item["module"]).split(".")[0].lstrip(".") and str(item["module"]).split(".")[0].lstrip(".") not in builtin_or_common and not str(item["module"]).startswith(("qgis", "PyQt", "."))})
    return {"plugin_name": plugin_name, "files_checked": len(files), "syntax_errors": syntax_errors, "qgis_imports": qgis_imports, "pyqt_imports": pyqt_imports, "relative_imports": relative_imports[:200], "external_import_candidates": external_candidates, "imports": imports[:1000], "valid": not syntax_errors, "note": "Static AST analysis only; plugin code was not executed."}


def check_plugin_resources(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _require_plugin(plugin_name)
    files = _relative_files(plugin_path)
    ui_files = [file for file in files if file.endswith(".ui")]
    qrc_files = [file for file in files if file.endswith(".qrc")]
    icon_files = [file for file in files if Path(file).suffix.lower() in ICON_EXTENSIONS]
    py_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in plugin_path.rglob("*.py") if "__pycache__" not in path.parts)
    suspicious_references = []
    for marker in [".ui", ".qrc", ".svg", ".png", ".ico"]:
        if marker in py_text and not any(file.endswith(marker) for file in files):
            suspicious_references.append(f"Python code references {marker}, but no {marker} file was found.")
    return {"plugin_name": plugin_name, "ui_files": ui_files, "qrc_files": qrc_files, "icon_files": icon_files, "resources_py_exists": (plugin_path / "resources.py").exists(), "suspicious_references": suspicious_references, "valid": not suspicious_references}


def check_plugin_icon(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _require_plugin(plugin_name)
    metadata = _read_metadata(plugin_path)
    icon_ref = metadata.get("icon", "")
    candidates = []
    if icon_ref:
        candidates.append(plugin_path / icon_ref)
    candidates.extend(path for path in _iter_files(plugin_path) if path.suffix.lower() in ICON_EXTENSIONS and "icon" in path.name.lower())
    found = []
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            found.append({"path": str(candidate), "size": candidate.stat().st_size, "valid_extension": candidate.suffix.lower() in ICON_EXTENSIONS, "non_empty": candidate.stat().st_size > 0})
    return {"plugin_name": plugin_name, "metadata_icon": icon_ref, "icons_found": found, "valid": bool(found) and all(item["valid_extension"] and item["non_empty"] for item in found)}


def check_plugin_runtime_status(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _find_plugin_path(plugin_name)
    data: dict[str, Any] = {"plugin_name": plugin_name, "installed": plugin_path is not None, "path": str(plugin_path) if plugin_path else ""}
    try:
        import qgis.utils  # type: ignore

        data["loaded"] = plugin_name in getattr(qgis.utils, "plugins", {})
        data["active"] = plugin_name in getattr(qgis.utils, "active_plugins", [])
        data["loaded_plugins"] = sorted(getattr(qgis.utils, "plugins", {}).keys())
    except Exception as exc:
        data["loaded"] = False
        data["active"] = False
        data["warning"] = f"Runtime plugin status was not available: {exc}"
    metadata = _read_metadata(plugin_path) if plugin_path else {}
    data["version"] = metadata.get("version", "")
    data["display_name"] = metadata.get("name", plugin_name)
    return data


def check_plugin_menu_actions(params: dict[str, Any], context: dict[str, Any]):
    return _check_actions(params, toolbar=False)


def check_plugin_toolbar_actions(params: dict[str, Any], context: dict[str, Any]):
    return _check_actions(params, toolbar=True)


def _check_actions(params: dict[str, Any], toolbar: bool) -> dict[str, Any]:
    plugin_name = require_param(params, "plugin_name", str)
    actions: list[dict[str, Any]] = []
    warning = ""
    try:
        import qgis.utils  # type: ignore

        plugin = getattr(qgis.utils, "plugins", {}).get(plugin_name)
        for name in dir(plugin) if plugin else []:
            value = getattr(plugin, name, None)
            if hasattr(value, "text") and callable(value.text):
                actions.append({"attribute": name, "text": value.text()})
            elif isinstance(value, list):
                for index, nested in enumerate(value):
                    if hasattr(nested, "text") and callable(nested.text):
                        actions.append({"attribute": f"{name}[{index}]", "text": nested.text()})
    except Exception as exc:
        warning = f"Could not inspect runtime actions: {exc}"
    return {"plugin_name": plugin_name, "action_source": "toolbar" if toolbar else "menu", "actions": actions, "warnings": [warning] if warning else [], "partial": True}


def check_processing_provider_registration(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    providers: list[dict[str, Any]] = []
    warning = ""
    try:
        from qgis.core import QgsApplication  # type: ignore

        registry = QgsApplication.processingRegistry()
        metadata = _read_metadata(_find_plugin_path(plugin_name) or Path())
        display_name = metadata.get("name", "")
        for provider in registry.providers():
            pid = provider.id()
            pname = provider.name()
            if _matches_plugin_provider(plugin_name, display_name, pid, pname):
                providers.append({"id": pid, "name": pname, "algorithm_count": len(provider.algorithms()), "algorithms": [alg.id() for alg in provider.algorithms()]})
    except Exception as exc:
        warning = f"Processing registry not available: {exc}"
    return {"plugin_name": plugin_name, "providers": providers, "warnings": [warning] if warning else []}


def check_plugin_algorithm_registration(params: dict[str, Any], context: dict[str, Any]):
    return check_processing_provider_registration(params, context)


def collect_plugin_logs(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = params.get("plugin_name", "")
    logger = context.get("logger")
    records = logger.tail(int(params.get("tail", 200))) if logger else []
    if plugin_name:
        lowered = str(plugin_name).lower()
        records = [record for record in records if lowered in str(record).lower()]
    return {"plugin_name": plugin_name, "logs": records}


def generate_plugin_report(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    output_path_raw = params.get("output_path", "")
    confirm_overwrite = bool(params.get("confirm_overwrite"))
    dry_run = bool(context.get("dry_run"))
    report = {
        "inspect": inspect_plugin({"plugin_name": plugin_name}, context),
        "metadata": validate_metadata_txt({"plugin_name": plugin_name}, context),
        "structure": check_plugin_structure({"plugin_name": plugin_name}, context),
        "imports": check_plugin_imports({"plugin_name": plugin_name}, context),
        "resources": check_plugin_resources({"plugin_name": plugin_name}, context),
        "icon": check_plugin_icon({"plugin_name": plugin_name}, context),
        "logs": collect_plugin_logs({"plugin_name": plugin_name, "tail": params.get("tail", 200)}, context),
        "runtime": check_plugin_runtime_status({"plugin_name": plugin_name}, context),
        "processing": check_processing_provider_registration({"plugin_name": plugin_name}, context),
    }
    errors = []
    warnings = []
    for section in report.values():
        if isinstance(section, dict):
            warnings.extend(section.get("warnings", []))
            if section.get("valid") is False:
                errors.append(f"{section.get('plugin_name', plugin_name)} has invalid {section}")
    summary = {"ready_for_publication": not errors, "warnings": warnings, "errors": errors, "recommendations": ["Review warnings before publishing.", "Run inside QGIS after packaging for runtime validation."]}
    payload = {"summary": summary, **report}
    if output_path_raw:
        output_path = _safe_output_path(str(output_path_raw))
        if dry_run:
            return {"plugin_name": plugin_name, "dry_run": True, "would_write": str(output_path), "report": payload}
        _write_markdown_report(output_path, f"SIGMAI Plugin Report - {plugin_name}", payload, confirm_overwrite)
        payload["output_path"] = str(output_path)
    return payload


def package_plugin_zip(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _require_plugin(plugin_name)
    output_path = _safe_output_path(require_param(params, "output_path", str))
    confirm_overwrite = bool(params.get("confirm_overwrite"))
    dry_run = bool(context.get("dry_run"))
    metadata_check = validate_metadata_txt({"plugin_name": plugin_name}, context)
    manifest = [str(Path(plugin_path.name) / item.relative_to(plugin_path)).replace("\\", "/") for item in _iter_files(plugin_path) if not _should_exclude(item, plugin_path)]
    if output_path.exists() and not confirm_overwrite and not dry_run:
        raise ValidationError("OUTPUT_EXISTS", "Output zip exists. Pass confirm_overwrite=true to replace it.", {"path": str(output_path)})
    if dry_run:
        return {"plugin_name": plugin_name, "dry_run": True, "output_path": str(output_path), "metadata_valid": metadata_check["valid"], "file_count": len(manifest), "manifest": manifest}
    if not metadata_check["valid"]:
        raise ValidationError("INVALID_METADATA", "metadata.txt must be valid before packaging.", metadata_check)
    manifest = _zip_plugin(plugin_path, output_path)
    return {"plugin_name": plugin_name, "output_path": str(output_path), "file_count": len(manifest), "manifest": manifest}


def install_plugin_from_folder(params: dict[str, Any], context: dict[str, Any]):
    return _install_or_update_from_folder(params, context, update=False)


def update_plugin_from_folder(params: dict[str, Any], context: dict[str, Any]):
    return _install_or_update_from_folder(params, context, update=True)


def _install_or_update_from_folder(params: dict[str, Any], context: dict[str, Any], update: bool):
    source = _safe_output_path(require_param(params, "source_folder", str))
    if not source.exists() or not source.is_dir():
        raise ValidationError("SOURCE_NOT_FOUND", "Source folder does not exist.", {"source_folder": str(source)})
    plugin_name = str(params.get("plugin_name") or source.name)
    existing = _find_plugin_path(plugin_name)
    if _is_self_plugin(plugin_name, existing):
        raise ValidationError("SELF_UPDATE_REQUIRES_SELF_MANAGEMENT", "This plugin is the running Bridge. Use self_stage_update and self_apply_update with backup.", {"plugin_name": plugin_name})
    destination_root = _plugin_roots()[-1]
    destination = destination_root / plugin_name
    try:
        resolved_destination = destination.resolve()
        resolved_root = destination_root.resolve()
        if resolved_destination != resolved_root and resolved_root not in resolved_destination.parents:
            raise ValidationError("PLUGIN_DESTINATION_BLOCKED", "Plugin destination escapes the QGIS plugin directory.", {"destination": str(destination)})
    except RuntimeError as exc:
        raise ValidationError("PLUGIN_DESTINATION_BLOCKED", "Could not validate plugin destination.", {"error": str(exc)}) from exc
    dry_run = bool(context.get("dry_run"))
    if destination.exists() and not update:
        raise ValidationError("PLUGIN_ALREADY_EXISTS", "Plugin already exists. Use update_plugin_from_folder.", {"destination": str(destination)})
    metadata = _metadata_errors(source)
    plan = {"source": str(source), "destination": str(destination), "update": update, "metadata_valid": metadata[0], "backup_required": destination.exists(), "restart_required": True}
    if dry_run:
        return {"dry_run": True, "plan": plan}
    backup = str(_backup_plugin(destination, plugin_name)) if destination.exists() else ""
    if destination.exists():
        shutil.rmtree(destination)
    copied = _copy_tree_safe(source, destination)
    return {"plan": plan, "backup_path": backup, "copied_files": copied, "restart_required": True}


def enable_plugin(params: dict[str, Any], context: dict[str, Any]):
    return _plugin_runtime_operation(params, "enable")


def disable_plugin(params: dict[str, Any], context: dict[str, Any]):
    return _plugin_runtime_operation(params, "disable")


def reload_plugin(params: dict[str, Any], context: dict[str, Any]):
    return _plugin_runtime_operation(params, "reload")


def uninstall_plugin(params: dict[str, Any], context: dict[str, Any]):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _require_plugin(plugin_name)
    if _is_self_plugin(plugin_name, plugin_path):
        raise ValidationError("SELF_UNINSTALL_BLOCKED", "The running Bridge cannot uninstall itself.", {"plugin_name": plugin_name})
    if context.get("dry_run"):
        return {"dry_run": True, "would_remove": str(plugin_path), "backup_required": True}
    backup = _backup_plugin(plugin_path, plugin_name)
    shutil.rmtree(plugin_path)
    return {"plugin_name": plugin_name, "removed_path": str(plugin_path), "backup_path": str(backup), "restart_required": True}


def _plugin_runtime_operation(params: dict[str, Any], operation: str):
    plugin_name = require_param(params, "plugin_name", str)
    plugin_path = _find_plugin_path(plugin_name)
    if _is_self_plugin(plugin_name, plugin_path):
        return {"plugin_name": plugin_name, "operation": operation, "applied": False, "restart_required": True, "warnings": ["Runtime changes to the running Bridge are intentionally not applied. Restart QGIS after staged self-management changes."]}
    try:
        import qgis.utils  # type: ignore

        if operation == "enable":
            result = qgis.utils.loadPlugin(plugin_name)
            if result:
                qgis.utils.startPlugin(plugin_name)
        elif operation == "disable":
            qgis.utils.unloadPlugin(plugin_name)
            result = True
        else:
            qgis.utils.unloadPlugin(plugin_name)
            result = qgis.utils.loadPlugin(plugin_name)
            if result:
                qgis.utils.startPlugin(plugin_name)
        return {"plugin_name": plugin_name, "operation": operation, "applied": bool(result), "restart_required": operation == "reload"}
    except Exception as exc:
        return {"plugin_name": plugin_name, "operation": operation, "applied": False, "warnings": [str(exc)], "restart_required": True}


def self_inspect(params: dict[str, Any], context: dict[str, Any]):
    plugin_path = _current_plugin_path()
    session = context.get("session", {})
    loaded = sorted(context.get("registered_actions", []))
    disk = _disk_declared_commands(plugin_path)
    return {
        "plugin_name": "sigmai",
        "path": str(plugin_path),
        "summary": _plugin_summary("sigmai", plugin_path),
        "session": session,
        "commands_available": loaded,
        "disk_declared_commands": sorted(disk),
        "runtime_missing_disk_commands": sorted(set(disk) - set(loaded)),
        "logs_tail": context.get("logger").tail(20) if context.get("logger") else [],
    }


def _disk_declared_commands(plugin_path: Path) -> set[str]:
    permissions_path = plugin_path / "permissions.py"
    if not permissions_path.exists():
        return set()
    try:
        text = permissions_path.read_text(encoding="utf-8")
    except Exception:
        return set()
    return set(re.findall(r'CommandPermission\("([^"]+)"', text))


def _restart_required_from_context(context: dict[str, Any]) -> dict[str, Any]:
    plugin_path = _current_plugin_path()
    loaded = set(context.get("registered_actions", []))
    disk = _disk_declared_commands(plugin_path)
    missing = sorted(disk - loaded)
    extra = sorted(loaded - disk)
    return {
        "restart_required": bool(missing),
        "disk_command_count": len(disk),
        "loaded_command_count": len(loaded),
        "runtime_missing_disk_commands": missing,
        "runtime_extra_commands": extra,
    }


def self_health_check(params: dict[str, Any], context: dict[str, Any]):
    restart = _restart_required_from_context(context)
    checks = {
        "inspect": self_inspect(params, context),
        "metadata": validate_metadata_txt({"plugin_name": "sigmai"}, context),
        "structure": check_plugin_structure({"plugin_name": "sigmai"}, context),
        "imports": check_plugin_imports({"plugin_name": "sigmai"}, context),
        "resources": check_plugin_resources({"plugin_name": "sigmai"}, context),
        "icon": check_plugin_icon({"plugin_name": "sigmai"}, context),
    }
    structure = checks["structure"]
    resources = checks["resources"]
    ok = all(
        (
            checks["metadata"].get("valid"),
            checks["imports"].get("valid"),
            checks["icon"].get("valid"),
            structure.get("checks", {}).get("metadata_txt"),
            structure.get("checks", {}).get("init_py"),
        )
    )
    warnings = []
    if structure.get("packaging_issues"):
        warnings.append("Runtime/generated files are present in the installed plugin folder; packaging excludes them from backups and ZIPs.")
    if resources.get("suspicious_references"):
        warnings.append("Resource scan found suspicious references; review before publication, but this does not block runtime health.")
    if restart["restart_required"]:
        warnings.append("Installed plugin files declare commands that are not loaded in the current QGIS runtime. Restart QGIS or re-enable SIGMAI.")
    return {"ok": ok, "checks": checks, "warnings": warnings, **restart}


def self_backup(params: dict[str, Any], context: dict[str, Any]):
    plugin_path = _current_plugin_path()
    dry_run = bool(context.get("dry_run"))
    manifest = [str(Path(plugin_path.name) / item.relative_to(plugin_path)).replace("\\", "/") for item in _iter_files(plugin_path) if not _should_exclude(item, plugin_path)]
    if dry_run:
        return {"dry_run": True, "plugin_path": str(plugin_path), "file_count": len(manifest), "manifest": manifest}
    backup = _backup_plugin(plugin_path, "sigmai")
    return {"plugin_path": str(plugin_path), "backup_path": str(backup), "file_count": len(manifest), "manifest": manifest}


def self_validate_update(params: dict[str, Any], context: dict[str, Any]):
    source = _safe_output_path(require_param(params, "source_folder", str))
    if not source.exists() or not source.is_dir():
        raise ValidationError("SOURCE_NOT_FOUND", "Source folder does not exist.", {"source_folder": str(source)})
    valid, missing, warnings, metadata = _metadata_errors(source)
    structure = {"metadata_txt": (source / "metadata.txt").exists(), "init_py": (source / "__init__.py").exists(), "plugin_py": (source / "plugin.py").exists()}
    changed_files = [str(path.relative_to(source)).replace("\\", "/") for path in _iter_files(source) if not _should_exclude(path, source)]
    return {"source_folder": str(source), "metadata_valid": valid, "missing_metadata_fields": missing, "warnings": warnings, "metadata": metadata, "structure": structure, "changed_files": changed_files[:1000], "valid": valid and structure["metadata_txt"] and structure["init_py"]}


def self_stage_update(params: dict[str, Any], context: dict[str, Any]):
    source = _safe_output_path(require_param(params, "source_folder", str))
    validation = self_validate_update({"source_folder": str(source)}, context)
    staging_root = _public_runtime_dir("staging")
    target = staging_root / "sigmai"
    if context.get("dry_run"):
        return {"dry_run": True, "would_stage": str(target), "validation": validation}
    if target.exists():
        shutil.rmtree(target)
    copied = _copy_tree_safe(source, target)
    return {"staged_path": str(target), "copied_files": copied, "validation": validation, "next_step": "Run self_backup, then self_apply_update with confirm_self_apply_update=true."}


def self_apply_update(params: dict[str, Any], context: dict[str, Any]):
    staging_root = _public_runtime_dir("staging") / "sigmai"
    if not staging_root.exists():
        raise ValidationError("STAGING_NOT_FOUND", "No staged SIGMAI update was found.", {"staging_path": str(staging_root)})
    plugin_path = _current_plugin_path()
    if context.get("dry_run"):
        return {"dry_run": True, "would_apply_from": str(staging_root), "would_apply_to": str(plugin_path), "backup_required": True, "restart_required": True}
    backup = _backup_plugin(plugin_path, "sigmai")
    copied = _copy_tree_safe(staging_root, plugin_path)
    return {"applied": True, "backup_path": str(backup), "copied_files": copied, "restart_required": True}


def self_restart_required(params: dict[str, Any], context: dict[str, Any]):
    restart = _restart_required_from_context(context)
    restart["note"] = "Restart is required after self_apply_update when installed commands differ from the loaded runtime registry."
    return restart


def self_rollback(params: dict[str, Any], context: dict[str, Any]):
    backup_path = _safe_output_path(require_param(params, "backup_path", str))
    if not backup_path.exists() or backup_path.suffix.lower() != ".zip":
        raise ValidationError("BACKUP_NOT_FOUND", "Backup zip was not found.", {"backup_path": str(backup_path)})
    if context.get("dry_run"):
        return {"dry_run": True, "would_restore": str(backup_path), "restart_required": True}
    plugin_path = _current_plugin_path()
    with zipfile.ZipFile(backup_path, "r") as archive:
        archive.extractall(plugin_path.parent)
    return {"restored_from": str(backup_path), "plugin_path": str(plugin_path), "restart_required": True}


def self_generate_report(params: dict[str, Any], context: dict[str, Any]):
    enriched = dict(params)
    enriched["plugin_name"] = "sigmai"
    return generate_plugin_report(enriched, context)
