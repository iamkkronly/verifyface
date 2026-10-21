"""The smallest possible verifyface program.

    python examples/01_hello_verify.py my_photo.jpg my_selfie.jpg

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import sys

import verifyface as vf


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    reference, probe = sys.argv[1], sys.argv[2]

    print(f"verifyface {vf.__version__} — Developer: {vf.__author__}\n")

    # 1. enroll (only needed once per person; it is idempotent here)
    enrollment = vf.enroll("demo-person", reference, overwrite=True)
    print(enrollment.explain())

    # 2. verify
    result = vf.verify("demo-person", probe)
    print(result.explain())

    # 3. show the numbers behind the decision
    print(f"\n  similarity : {result.score:+.3f}")
    print(f"  threshold  : {result.threshold:.3f} ({result.threshold_name})")
    print(f"  confidence : {result.confidence:.1%}")
    print(f"  quality    : {result.quality.describe()}")

    # 4. tidy up
    vf.remove("demo-person")
    return 0 if result.matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
