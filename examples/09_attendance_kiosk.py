"""Attendance kiosk: one camera, everyone walks past, results go to a CSV.

    python examples/09_attendance_kiosk.py            # press q to quit

This is the pattern used by schools and small offices. It demonstrates:

* enrolling several people (run ``--enroll`` first),
* identifying a person from a live frame,
* a cooldown so one person is not logged ten times a second,
* a CSV log that is safe to keep (names and times, never photos).

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import verifyface as vf

LOG = Path("attendance.csv")
COOLDOWN_SECONDS = 30


def enroll(verifier: vf.Verifier) -> None:
    print("Enter names and photos, one per line. Empty name to finish.")
    while True:
        name = input("Name: ").strip()
        if not name:
            break
        photo = input("Photo path: ").strip().strip('"')
        try:
            print(" ", verifier.enroll(name, photo, overwrite=True).explain())
        except vf.VerifyFaceError as exc:
            print("  problem:", exc)


def capture(verifier: vf.Verifier, camera: int) -> None:
    import cv2

    cap = vf.open_camera(camera)
    last_seen: dict[str, float] = {}
    if not LOG.exists():
        with LOG.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(["timestamp", "identity", "similarity"])

    print("Kiosk running — press q in the preview window to quit.")
    try:
        while True:
            frame = vf.read_frame(cap)
            frame = cv2.flip(frame, 1)
            label = "Looking for a face…"
            colour = (200, 200, 200)

            try:
                match = verifier.identify(frame)
                if match.matched and match.identity:
                    label = f"{match.identity}  ({match.score:.2f})"
                    colour = (0, 200, 0)
                    now = time.time()
                    if now - last_seen.get(match.identity, 0) > COOLDOWN_SECONDS:
                        last_seen[match.identity] = now
                        with LOG.open("a", newline="", encoding="utf-8") as handle:
                            csv.writer(handle).writerow(
                                [datetime.now().isoformat(timespec="seconds"),
                                 match.identity, round(match.score, 4)]
                            )
                        print(f"  ✔ {match.identity} at {datetime.now():%H:%M:%S}")
                elif match.ranking:
                    label = f"Unknown (closest {match.ranking[0][0]} {match.score:.2f})"
                    colour = (60, 60, 220)
            except vf.VerifyFaceError:
                pass

            cv2.rectangle(frame, (0, 0), (frame.shape[1], 46), (20, 20, 20), -1)
            cv2.putText(frame, label, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)
            cv2.putText(frame, "verifyface · Developer: Kaustav Kanti Ray", (12, 68),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 150, 150), 1)
            cv2.imshow("verifyface attendance", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main() -> int:
    parser = argparse.ArgumentParser(description="verifyface attendance kiosk")
    parser.add_argument("--enroll", action="store_true", help="add people before running")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--vault", default="kiosk-vault")
    args = parser.parse_args()

    print(f"{vf.BANNER}\n")
    verifier = vf.Verifier(vault=args.vault, threshold="strict")

    if args.enroll or not verifier.identities():
        enroll(verifier)
    if not verifier.identities():
        print("Nobody enrolled — nothing to do.")
        return 1

    print(f"Enrolled: {', '.join(verifier.identities())}")
    capture(verifier, args.camera)
    print(f"Log written to {LOG.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
