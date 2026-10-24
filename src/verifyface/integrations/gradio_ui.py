"""Gradio adapter — webcam + upload verification in a few lines.

    from verifyface.integrations.gradio_ui import build
    build().launch()          # opens http://127.0.0.1:7860

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

from typing import Optional

from ..verify import Verifier


def build(verifier: Optional[Verifier] = None, *, title: str = "verifyface"):
    """Return a :class:`gradio.Blocks` app wired to verifyface."""
    try:
        import gradio as gr
    except ImportError:  # pragma: no cover - optional dependency
        raise ImportError("Gradio is not installed. Run: pip install gradio") from None

    from ..errors import VerifyFaceError

    service = verifier or Verifier()

    def do_verify(name: str, image_path: str):
        if not name or not image_path:
            return "Choose a person and an image.", ""
        try:
            result = service.verify(name, image_path)
            return ("VERIFIED — " if result.matched else "NOT verified — ") + result.explain(), \
                   result.as_dict()
        except VerifyFaceError as exc:
            return str(exc), ""

    def do_enroll(name: str, image_path: str):
        if not name or not image_path:
            return "Enter a name and add at least one photo."
        try:
            return service.enroll(name, [image_path], overwrite=True).explain()
        except VerifyFaceError as exc:
            return str(exc)

    def do_identify(image_path: str):
        if not image_path:
            return "Add a photo first."
        try:
            return service.identify(image_path).explain()
        except VerifyFaceError as exc:
            return str(exc)

    with gr.Blocks(title=title) as demo:
        gr.Markdown(
            f"# {title}\nOffline face verification · **Developer: Kaustav Kanti Ray**"
        )
        with gr.Tab("Verify"):
            name = gr.Dropdown(choices=service.identities(), label="Person", allow_custom_value=False)
            with gr.Row():
                webcam = gr.Image(sources=["webcam"], type="filepath", label="Webcam")
                upload = gr.Image(sources=["upload"], type="filepath", label="Upload")
            out_text = gr.Textbox(label="Result", lines=2)
            out_json = gr.JSON(label="Details")
            gr.Button("Verify", variant="primary").click(
                do_verify, inputs=[name, upload], outputs=[out_text, out_json]
            )
            gr.Button("Verify webcam").click(
                do_verify, inputs=[name, webcam], outputs=[out_text, out_json]
            )
        with gr.Tab("Enroll"):
            new_name = gr.Textbox(label="Name (any language)")
            enroll_image = gr.Image(sources=["upload", "webcam"], type="filepath", label="Photo")
            enroll_out = gr.Textbox(label="Result", lines=2)
            gr.Button("Enroll", variant="primary").click(
                do_enroll, inputs=[new_name, enroll_image], outputs=[enroll_out]
            )
        with gr.Tab("Identify"):
            id_image = gr.Image(sources=["upload", "webcam"], type="filepath", label="Photo")
            id_out = gr.Textbox(label="Result", lines=2)
            gr.Button("Who is this?").click(do_identify, inputs=[id_image], outputs=[id_out])

    return demo


__all__ = ["build"]
