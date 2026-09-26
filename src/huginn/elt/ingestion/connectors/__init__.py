"""Thin clients for the third-party APIs the adapters read. One connector
per external API, constructed in `huginn.elt.ingestion.__main__.build_service`
and injected into the adapter that uses it. These modules hold no ingestion
policy, unlike `adapters/`.
"""
