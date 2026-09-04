"""Interface do SIGMAI dentro do QGIS."""

from .client_configs import AI_CLIENTS, build_client_config, config_file_hint

__all__ = ["AI_CLIENTS", "build_client_config", "config_file_hint"]
