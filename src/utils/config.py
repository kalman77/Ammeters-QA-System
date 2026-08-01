"""Compatibility import for the pre-refactor configuration API."""

from src.infrastructure.config.load_yaml_config import (
    load_yaml_config as load_config,
)

__all__ = ["load_config"]
