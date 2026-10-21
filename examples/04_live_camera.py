"""Live camera verification with random anti-spoofing challenges.

    python examples/04_live_camera.py                # capture a test frame
    python examples/04_live_camera.py enroll kaustav  # enroll from the camera
    python examples/04_live_camera.py verify kaustav  # verify from the camera

Needs a camera and, for the on-screen window,
``pip install "verifyface[camera]"``.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import sys

import verifyface as vf


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "capture"
    identity = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"verifyface {vf.__version__} — Developer: {vf.__author__}\n")

    if mode == "capture":
        result = vf.scan_live(mode="capture", actions=2, timeout=20)
        print(result.message)
        if result.best_frame is not None:
            path = "captured.jpg"
            import cv2

            cv2.imwrite(path, result.best_frame)
            print(f"Saved the best frame to {path}")
        return 0 if result.passed else 1

    if mode not in {"enroll", "verify"}:
        print(__doc__)
        return 2
    if not identity:
        print("Please give a name:  python 04_live_camera.py verify kaustav")
        return 2

    verifier = vf.Verifier(vault="demo-vault")

    if mode == "verify" and not verifier.enrolled(identity):
        print(f"{identity!r} is not enrolled yet — run the enroll mode first.")
        return 2

    # The desktop helper drives the same state machine for you:
    result = vf.scan_live(
        identity=identity,
        verifier=verifier,
        mode=mode,
        actions=2,
        timeout=25,
    )
    print(result.message)
    print(f"liveness: {result.liveness.explain()}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
