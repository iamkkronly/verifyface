"""Compare two photos without enrolling anybody.

    python examples/03_compare_two_photos.py before.jpg after.jpg

Nothing is written to disk.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import sys

import verifyface as vf


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    a, b = sys.argv[1], sys.argv[2]
    print(f"verifyface {vf.__version__} — Developer: {vf.__author__}\n")
    print(f"  A: {a}\n  B: {b}\n")

    verifier = vf.Verifier(vault="demo-vault")
    try:
        result = verifier.compare(a, b)
    except vf.VerifyFaceError as exc:
        print(f"Could not compare: {exc}")
        return 2

    print(result.explain())
    print()
    for label, quality in (("A", result.quality_a), ("B", result.quality_b)):
        if quality is not None:
            print(f"  quality {label}: {quality.describe()}")

    print("\nInterpretation:")
    score = result.score
    if score >= 0.55:
        print("  Very strong match — almost certainly the same person.")
    elif score >= 0.48:
        print("  Strong match — the same person, with different conditions.")
    elif score >= 0.40:
        print("  Match at the balanced threshold.")
    elif score >= 0.30:
        print("  Borderline — try better photos, or enroll both and compare.")
    else:
        print("  Different people.")

    print("\nTry a different policy:  --threshold strict | balanced | lenient")
    return 0 if result.matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
