"""Enroll a whole folder of people, one photo each, then test them.

    python examples/02_enroll_from_folder.py photos/ test/

Folder layout:
    photos/kaustav.jpg     → enrolled as "kaustav"
    photos/riya-1.jpg      → enrolled as "riya" (suffix "-1" is stripped)
    photos/riya-2.jpg      → second sample for "riya"

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import verifyface as vf

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def person_name(path: Path) -> str:
    stem = path.stem
    if "-" in stem and stem.rsplit("-", 1)[-1].isdigit():
        stem = stem.rsplit("-", 1)[0]
    return stem.replace("_", " ").strip()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    source = Path(sys.argv[1])
    verifier = vf.Verifier(vault="demo-vault")

    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(source.iterdir()):
        if path.suffix.lower() in EXTENSIONS:
            grouped[person_name(path)].append(path)

    if not grouped:
        print(f"No images found in {source}")
        return 1

    print(f"verifyface {vf.__version__} — Developer: {vf.__author__}\n")

    ok = 0
    for name, photos in grouped.items():
        try:
            result = verifier.enroll(name, photos, overwrite=True)
            ok += 1
            print(f"  ✔ {result.explain()}")
        except vf.VerifyFaceError as exc:
            print(f"  ✘ {name}: {exc}")

    print(f"\nEnrolled {ok}/{len(grouped)} people into {verifier.vault.path}")

    if len(sys.argv) > 2:
        test_folder = Path(sys.argv[2])
        print(f"\nChecking every enrolled person against {test_folder}:")
        for name in verifier.identities():
            candidates = [
                p for p in test_folder.iterdir()
                if p.suffix.lower() in EXTENSIONS and person_name(p) == name
            ]
            for photo in candidates:
                result = verifier.verify(name, photo)
                mark = "✔" if result.matched else "✘"
                print(f"  {mark} {name:20s} {photo.name:24s} {result.score:+.3f}")

        print("\nIdentifying every test photo:")
        for photo in sorted(test_folder.iterdir()):
            if photo.suffix.lower() not in EXTENSIONS:
                continue
            try:
                match = verifier.identify(photo)
                who = match.identity or "unknown"
                print(f"  {photo.name:24s} → {who:20s} ({match.score:+.3f})")
            except vf.VerifyFaceError as exc:
                print(f"  {photo.name:24s} → {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
