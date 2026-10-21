"""Drop-in adapters for the most common Python frameworks.

Every adapter is optional: nothing is imported until you use it, and a missing
framework produces a clear message instead of an ImportError traceback.

    from verifyface.integrations.fastapi_ext import install
    install(app)

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

__all__ = ["fastapi_ext", "flask_ext", "streamlit_ui", "gradio_ui", "django_views"]
