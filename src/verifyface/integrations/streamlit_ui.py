"""Streamlit adapter — a full face-verification page in one call.

    import streamlit as st
    from verifyface.integrations.streamlit_ui import render

    render()          # camera input, upload, enroll and verify — all built in

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

from typing import Optional

from ..verify import Verifier


def render(verifier: Optional[Verifier] = None, *, title: str = "Face verification") -> None:
    """Draw the verifyface UI inside a Streamlit app."""
    try:
        import streamlit as st
    except ImportError:  # pragma: no cover - optional dependency
        raise ImportError("Streamlit is not installed. Run: pip install streamlit") from None

    from ..errors import VerifyFaceError

    service = verifier or Verifier()

    st.title(title)
    st.caption("verifyface — Developer: Kaustav Kanti Ray · runs fully offline")

    people = service.identities()
    tab_verify, tab_enroll, tab_people = st.tabs(["Verify", "Enroll", "People"])

    with tab_verify:
        name = st.selectbox("Person", people or ["(nobody enrolled yet)"], key="vf-verify-name")
        source = st.radio("Source", ["Upload a photo", "Camera"], horizontal=True, key="vf-source")
        image = None
        if source == "Upload a photo":
            upload = st.file_uploader("Photo", type=["jpg", "jpeg", "png", "webp"], key="vf-upload")
            image = upload.read() if upload else None
        else:
            shot = st.camera_input("Take a photo", key="vf-camera")
            image = shot.read() if shot else None

        if st.button("Verify", type="primary", disabled=not image or not people, key="vf-verify"):
            try:
                result = service.verify(name, image)
                if result.matched:
                    st.success(result.explain())
                else:
                    st.error(result.explain())
                st.json(result.as_dict())
            except VerifyFaceError as exc:
                st.warning(str(exc))

        st.divider()
        if st.button("Who is this?", disabled=not image, key="vf-identify"):
            try:
                result = service.identify(image)
                (st.success if result.matched else st.info)(result.explain())
                st.table({"person": [n for n, _ in result.ranking],
                          "similarity": [round(s, 3) for _, s in result.ranking]})
            except VerifyFaceError as exc:
                st.warning(str(exc))

    with tab_enroll:
        new_name = st.text_input("Name (any language)", key="vf-enroll-name")
        uploads = st.file_uploader(
            "1–3 photos", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True,
            key="vf-enroll-files",
        )
        overwrite = st.checkbox("Replace existing profile", value=True, key="vf-overwrite")
        if st.button("Enroll", type="primary", disabled=not new_name or not uploads, key="vf-enroll"):
            try:
                result = service.enroll(
                    new_name, [u.read() for u in uploads], overwrite=overwrite
                )
                st.success(result.explain())
            except VerifyFaceError as exc:
                st.warning(str(exc))

    with tab_people:
        if not people:
            st.info("Nobody enrolled yet.")
        for person in people:
            profile = service.profile(person)
            col_a, col_b = st.columns([4, 1])
            col_a.write(
                f"**{person}** — {profile.sample_count} sample(s), "
                f"self-consistency {profile.self_similarity:.2f}"
            )
            if col_b.button("Delete", key=f"del-{person}"):
                service.remove(person)
                st.rerun()


__all__ = ["render"]
