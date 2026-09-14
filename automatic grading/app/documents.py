"""Public PDF service interface: permissively licensed local rendering and reports.

Worksheet originals are immutable; report backgrounds use rendered pages with
vector answer ink and marks. The existing generator PDF exporter is unaffected.
"""
from .documents_permissive import MAX_BYTES, MAX_PAGES, MAX_PAGE_POINTS, import_pdf, render_upload_pages, report_pdf

__all__ = ["MAX_BYTES", "MAX_PAGES", "MAX_PAGE_POINTS", "import_pdf", "render_upload_pages", "report_pdf"]
