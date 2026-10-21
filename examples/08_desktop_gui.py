"""A desktop app with Tkinter — no browser, no extra packages.

    python examples/08_desktop_gui.py

Enroll from a file or the camera, then verify from a file or the camera.
Works on Windows, macOS and Linux (Tkinter ships with python.org builds; on
Debian/Ubuntu install ``python3-tk``).

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import verifyface as vf

BG = "#0b1020"
PANEL = "#141b33"
LINE = "#26314f"
TEXT = "#e9eefc"
MUTED = "#9aa7c7"
ACCENT = "#6c8cff"

FILETYPES = [("Images", "*.jpg *.jpeg *.png *.webp *.bmp"), ("All files", "*.*")]


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.verifier = vf.Verifier(vault="demo-vault")
        root.title("verifyface — Developer: Kaustav Kanti Ray")
        root.configure(bg=BG)
        root.geometry("560x470")
        root.resizable(False, False)

        title = tk.Label(root, text="verifyface", font=("Segoe UI", 22, "bold"),
                         bg=BG, fg=TEXT)
        title.pack(pady=(22, 2))
        tk.Label(root, text="Offline face verification · Developer: Kaustav Kanti Ray",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(pady=(0, 18))

        card = tk.Frame(root, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=26, pady=(0, 20))

        tk.Label(card, text="Name (any language)", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(18, 4))
        self.name = tk.Entry(card, font=("Segoe UI", 12), bg="#0d1428", fg=TEXT,
                             insertbackground=TEXT, relief="flat")
        self.name.pack(fill="x", padx=18, ipady=7)
        self.name.insert(0, "kaustav")

        row1 = tk.Frame(card, bg=PANEL)
        row1.pack(fill="x", padx=18, pady=(16, 0))
        self._button(row1, "Enroll from file", self.enroll_file).pack(side="left")
        self._button(row1, "Enroll from camera", self.enroll_camera).pack(side="left", padx=8)

        row2 = tk.Frame(card, bg=PANEL)
        row2.pack(fill="x", padx=18, pady=(10, 0))
        self._button(row2, "Verify from file", self.verify_file).pack(side="left")
        self._button(row2, "Verify with camera", self.verify_camera).pack(side="left", padx=8)

        tk.Label(card, text="Enrolled people", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(20, 4))
        self.people = tk.Listbox(card, height=4, bg="#0d1428", fg=TEXT, relief="flat",
                                 highlightthickness=0, font=("Segoe UI", 10))
        self.people.pack(fill="x", padx=18)

        self.status = tk.Label(card, text="Ready.", bg=PANEL, fg=MUTED, justify="left",
                               wraplength=470, font=("Segoe UI", 10))
        self.status.pack(anchor="w", padx=18, pady=14)

        self.refresh()

    # -- helpers --------------------------------------------------------- #
    def _button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=ACCENT, fg="#08122e",
                         activebackground="#8aa2ff", relief="flat", font=("Segoe UI", 10, "bold"),
                         padx=14, pady=7, cursor="hand2")

    def refresh(self) -> None:
        self.people.delete(0, "end")
        for name in self.verifier.identities():
            self.people.insert("end", name)

    def current_name(self) -> str:
        name = self.name.get().strip()
        if not name:
            messagebox.showwarning("verifyface", "Please type a name first.")
        return name

    def say(self, text: str) -> None:
        self.status.config(text=text)

    def run_async(self, work, done) -> None:
        def runner():
            try:
                result = work()
            except vf.VerifyFaceError as exc:
                message = f"Problem: {exc}"
                self.root.after(0, lambda text=message: self.say(text))
                return
            except Exception as exc:  # pragma: no cover
                message = f"Unexpected error: {exc}"
                self.root.after(0, lambda text=message: self.say(text))
                return
            self.root.after(0, lambda value=result: done(value))

        self.say("Working…")
        threading.Thread(target=runner, daemon=True).start()

    # -- actions --------------------------------------------------------- #
    def enroll_file(self) -> None:
        name = self.current_name()
        if not name:
            return
        paths = filedialog.askopenfilenames(title="Choose 1–3 photos", filetypes=FILETYPES)
        if not paths:
            return
        self.run_async(
            lambda: self.verifier.enroll(name, list(paths), overwrite=True),
            lambda result: (self.say(result.explain()), self.refresh()),
        )

    def enroll_camera(self) -> None:
        name = self.current_name()
        if not name:
            return
        self.run_async(
            lambda: vf.scan_live(identity=name, verifier=self.verifier, mode="enroll", actions=2),
            lambda result: (self.say(result.message), self.refresh()),
        )

    def verify_file(self) -> None:
        name = self.current_name()
        if not name:
            return
        path = filedialog.askopenfilename(title="Choose a photo", filetypes=FILETYPES)
        if not path:
            return
        if not self.verifier.enrolled(name):
            messagebox.showwarning("verifyface", f"{name!r} is not enrolled yet.")
            return
        self.run_async(lambda: self.verifier.verify(name, path),
                       lambda result: self.say(result.explain()))

    def verify_camera(self) -> None:
        name = self.current_name()
        if not name:
            return
        if not self.verifier.enrolled(name):
            messagebox.showwarning("verifyface", f"{name!r} is not enrolled yet.")
            return
        self.run_async(
            lambda: vf.scan_live(identity=name, verifier=self.verifier, mode="verify", actions=2),
            lambda result: self.say(result.message),
        )


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
