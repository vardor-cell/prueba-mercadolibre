"""Pipeline ingest: sube los CSV raw locales a BigQuery (l1)."""
from .pipeline import create_pipeline

__all__ = ["create_pipeline"]
