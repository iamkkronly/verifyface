"""A complete Streamlit face-verification page.

    pip install streamlit "verifyface[secure]"
    streamlit run examples/07_streamlit_app.py

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import verifyface as vf

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    raise SystemExit("Streamlit is not installed. Run: pip install streamlit")

from verifyface.integrations.streamlit_ui import render

st.set_page_config(page_title="verifyface", page_icon="🙂", layout="centered")

# One shared verifier for the whole Streamlit session
@st.cache_resource
def get_verifier() -> vf.Verifier:
    return vf.Verifier(vault="demo-vault", threshold="balanced")


render(get_verifier())

st.divider()
with st.expander("How it works"):
    st.markdown(
        """
1. **Enroll** a person from 1–3 photos — only 128 numbers per photo are stored.
2. **Verify** any later photo: the face is aligned on five landmarks and
   compared with the stored identity vector.
3. Different clothes, places, cameras and even years are fine — the embedding
   describes facial geometry, not appearance.

*Nothing leaves this machine, and the photos themselves are never stored.*
        """
    )
st.caption(f"verifyface {vf.__version__} · Developer: {vf.__author__}")
