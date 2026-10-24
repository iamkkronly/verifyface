"""Command line interface — no programming required.

    verifyface enroll kaustav photo1.jpg photo2.jpg
    verifyface verify kaustav selfie.jpg
    verifyface identify photo.jpg
    verifyface compare before.jpg after.jpg
    verifyface list
    verifyface doctor
    verifyface serve            # browser app with camera + upload

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import _meta
from .config import THRESHOLD_PRESETS, default_vault_path
from .errors import VerifyFaceError

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
RESET = "\033[0m"


def _force_utf8_streams() -> None:
    """Make unicode output safe on Windows consoles.

    A Windows console redirected to a pipe defaults to the ANSI code page
    (cp1252, cp437 …), where ``✔`` and Bengali names raise UnicodeEncodeError.
    Reconfiguring to UTF-8 with ``errors="replace"`` keeps the command usable
    everywhere instead of crashing halfway through a message.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # very old interpreters / exotic streams
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - closed or detached stream
            pass


def _supports_colour() -> bool:
    return sys.stdout.isatty() and not (sys.platform.startswith("win") and "ANSICON" not in __import__("os").environ)


def _paint(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}" if _supports_colour() else text


def _ok(text: str) -> str:
    return _paint("✔ " + text, GREEN)


def _bad(text: str) -> str:
    return _paint("✘ " + text, RED)


def _warn(text: str) -> str:
    return _paint("! " + text, YELLOW)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_enroll(args: argparse.Namespace) -> int:
    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault, threshold=args.threshold)
    result = verifier.enroll(args.identity, list(args.images), overwrite=args.overwrite)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(_ok(result.explain()))
        for skipped in result.skipped_images:
            print(_warn(f"no usable face in {skipped}"))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault, threshold=args.threshold)
    pin = args.pin
    if pin is None and getattr(args, "ask_pin", False):
        import getpass

        pin = getpass.getpass("PIN: ")
    result = verifier.verify(
        args.identity,
        args.image,
        pin=pin,
        liveness=getattr(args, "liveness", "off"),
        ambiguity_guard=None if args.ambiguity_guard else False,
    )
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    else:
        line = result.explain()
        print(_ok(line) if result.matched else _bad(line))
        for reason in result.reasons:
            print(_warn(reason))
        if result.quality is not None and not result.quality.passed:
            print(_warn(f"photo quality: {result.quality.describe()}"))
    return 0 if result.matched else 1


def cmd_pin(args: argparse.Namespace) -> int:
    """Attach a second factor (PIN / passphrase) to an enrolled identity."""
    import getpass

    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault)
    if not verifier.enrolled(args.identity):
        print(_bad(f"no enrolled identity named {args.identity!r}"))
        return 1
    first = args.pin or getpass.getpass("New PIN: ")
    if args.pin is None:
        second = getpass.getpass("Repeat PIN: ")
        if first != second:
            print(_bad("the two PINs do not match"))
            return 1
    try:
        verifier.set_pin(args.identity, first)
    except vf.VerifyFaceError as exc:
        print(_bad(str(exc)))
        return 1
    print(_ok(f"PIN set for {args.identity!r} — verification now needs the PIN too"))
    pair = [p for p in verifier.lookalikes() if args.identity in (p[0], p[1])]
    if pair:
        print(_warn("this identity looks very similar to: " + ", ".join(
            f"{b if a == args.identity else a} ({score:.2f})" for a, b, score in pair
        )))
    return 0


def cmd_clear_pin(args: argparse.Namespace) -> int:
    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault)
    if not verifier.enrolled(args.identity):
        print(_bad(f"no enrolled identity named {args.identity!r}"))
        return 1
    verifier.clear_pin(args.identity)
    print(_ok(f"PIN removed for {args.identity!r}"))
    return 0


def cmd_lookalikes(args: argparse.Namespace) -> int:
    """Report enrolled pairs that are too similar to separate reliably."""
    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault)
    pairs = verifier.lookalikes(threshold=args.threshold)
    if args.json:
        print(json.dumps(
            [{"a": a, "b": b, "score": round(s, 4)} for a, b, s in pairs], indent=2,
            ensure_ascii=False,
        ))
        return 0
    names = verifier.identities()
    if not names:
        print(_warn(f"nobody enrolled in {verifier.vault.path}"))
        return 0
    if not pairs:
        print(_ok(f"{len(names)} identities, no lookalike pairs above {args.threshold:.2f}"))
        return 0
    print(_warn(f"{len(pairs)} lookalike pair(s) — twins/siblings score high here:"))
    for a, b, score in pairs:
        guarded = "guarded" if verifier.ambiguity_guard else "NOT guarded"
        print(f"  • {a} ↔ {b}  {score:.3f}  ({guarded})")
    print(_paint(
        "  Advice: keep the ambiguity guard on and set a PIN for both people: "
        "verifyface pin <name>", DIM,
    ))
    return 0


def cmd_identify(args: argparse.Namespace) -> int:
    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault, threshold=args.threshold)
    result = verifier.identify(args.image)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
        return 0 if result.matched else 1
    if result.matched:
        print(_ok(result.explain()))
        for name, score in result.ranking[1:3]:
            print(_paint(f"  next: {name} ({score:.3f})", DIM))
    else:
        print(_bad(result.explain()))
        for name, score in result.ranking[:3]:
            print(_paint(f"  closest: {name} ({score:.3f})", DIM))
    return 0 if result.matched else 1


def cmd_compare(args: argparse.Namespace) -> int:
    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault, threshold=args.threshold)
    result = verifier.compare(args.image_a, args.image_b)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(_ok(result.explain()) if result.matched else _bad(result.explain()))
    return 0 if result.matched else 1


def cmd_list(args: argparse.Namespace) -> int:
    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault)
    names = verifier.identities()
    if args.json:
        payload = []
        for name in names:
            try:
                payload.append(verifier.profile(name).as_dict())
            except Exception as exc:  # corrupted, unreadable
                payload.append({"identity": name, "error": str(exc)})
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if not names:
        print(_warn(f"no enrolled identities in {verifier.vault.path}"))
        return 0
    print(_paint(f"vault: {verifier.vault.path}", DIM))
    for name in names:
        try:
            profile = verifier.profile(name)
            extra = ""
            if profile.repaired:
                extra = " " + _warn("restored from backup")
            lock = " 🔒 PIN" if profile.has_pin else ""
            print(
                f"  • {name}{extra}{lock}  "
                + _paint(
                    f"{profile.sample_count} sample(s), self-consistency "
                    f"{profile.self_similarity:.2f}, updated {profile.updated_at}",
                    DIM,
                )
            )
        except Exception as exc:
            print(_bad(f"{name}: {exc}"))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault)
    if not verifier.enrolled(args.identity):
        print(_warn(f"no enrolled identity named {args.identity!r}"))
        return 1
    if not args.yes:
        answer = input(f"Delete the face profile for {args.identity!r}? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("cancelled")
            return 1
    verifier.remove(args.identity)
    print(_ok(f"deleted {args.identity!r}"))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import platform

    import numpy

    import verifyface as vf

    verifier = vf.Verifier(vault=args.vault)
    report = {
        "library": _meta.__version__,
        "developer": _meta.__author__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": numpy.__version__,
        "vault": str(verifier.vault.path),
        "checks": {},
    }
    problems = 0

    try:
        import cv2

        report["opencv"] = cv2.__version__
    except Exception as exc:  # pragma: no cover
        report["opencv"] = f"missing ({exc})"
        problems += 1

    try:
        report["pillow"] = __import__("PIL").__version__
    except Exception:  # pragma: no cover
        report["pillow"] = "missing"

    try:
        from .security import encryption_status, fingerprint, load_or_create_key

        key = load_or_create_key(verifier.vault.path)
        report["key_fingerprint"] = fingerprint(key)
        report["template_encryption"] = encryption_status()
    except Exception as exc:
        report["template_encryption"] = f"unavailable ({exc})"
        problems += 1

    try:
        engine_info = verifier.engine.info()
        report["models"] = engine_info["models"]
        for info in engine_info["models"].values():
            if not info["valid"]:
                problems += 1
    except Exception as exc:
        report["models"] = {"error": str(exc)}
        problems += 1

    try:
        integrity = verifier.vault.verify_integrity()
        report["templates"] = integrity
        problems += sum(1 for row in integrity if row["status"] == "corrupted")
    except Exception as exc:
        report["templates"] = [{"status": "error", "detail": str(exc)}]
        problems += 1

    try:
        report["lookalikes"] = [
            {"a": a, "b": b, "score": round(score, 4)} for a, b, score in verifier.lookalikes()
        ]
        report["second_factors"] = sum(
            1 for name in verifier.identities()
            if _safe_has_pin(verifier, name)
        )
    except Exception as exc:  # pragma: no cover - defensive
        report["lookalikes"] = []
        report["second_factors"] = 0
        report["lookalike_error"] = str(exc)

    report["camera"] = _camera_status()
    report["problems"] = problems

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if problems == 0 else 1

    print(_paint(_meta.BANNER, GREEN))
    print(_paint(f"python {report['python']} • {report['platform']}", DIM))
    print()
    for kind, info in report["models"].items():
        state = _ok("model ready") if info.get("valid") else _bad("model missing")
        print(f"  {kind:11s} {state}  {info.get('file', '')} {info.get('size_mb', '')} MB")
    print(f"  {'vault':11s} {report['vault']}")
    print(f"  {'encryption':11s} {report['template_encryption']}")
    print(f"  {'camera':11s} {report['camera']}")
    templates = report["templates"]
    if templates:
        bad = [t for t in templates if t["status"] == "corrupted"]
        fixed = [t for t in templates if t["status"] == "repaired"]
        print(f"  {'templates':11s} {len(templates)} checked, {len(fixed)} repaired, {len(bad)} corrupted")
    else:
        print(f"  {'templates':11s} none yet")
    pairs = report.get("lookalikes") or []
    if pairs:
        print(f"  {'lookalikes':11s} {len(pairs)} pair(s) need a second factor:")
        for row in pairs[:5]:
            print(_warn(f"      {row['a']} ↔ {row['b']}  {row['score']:.3f}"))
    else:
        print(f"  {'lookalikes':11s} none")
    if report.get("second_factors"):
        print(f"  {'2nd factor':11s} {report['second_factors']} identity(ies) protected by a PIN")
    print()
    if problems:
        print(_bad(f"{problems} problem(s) found — see details above"))
        return 1
    print(_ok("everything looks good"))
    return 0


def _safe_has_pin(verifier, name: str) -> bool:
    try:
        return bool(verifier.profile(name).has_pin)
    except Exception:
        return False


def _camera_status() -> str:
    try:
        import cv2
    except Exception:  # pragma: no cover
        return "opencv missing"
    try:
        capture = cv2.VideoCapture(0)
        opened = capture.isOpened()
        capture.release()
        return "available (#0)" if opened else "not detected (photo upload still works)"
    except Exception:
        return "not detected (photo upload still works)"


def cmd_download_models(args: argparse.Namespace) -> int:
    from .engine import download_models, resolve_model_dir

    target = Path(args.dir).expanduser() if args.dir else None
    folder = download_models(target, force=args.force)
    print(_ok(f"models ready in {folder}"))
    try:
        resolved = resolve_model_dir(folder)
        print(_paint(f"resolved: {resolved}", DIM))
    except VerifyFaceError as exc:
        print(_bad(str(exc)))
        return 1
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .web import serve

    return serve(host=args.host, port=args.port, vault=args.vault, open_browser=args.open)


def cmd_demo(args: argparse.Namespace) -> int:
    import verifyface as vf

    try:
        result = vf.scan_live(mode="capture", camera=args.camera, actions=args.actions)
    except VerifyFaceError as exc:
        print(_bad(str(exc)))
        return 1
    print(_ok(result.message) if result.passed else _bad(result.message))
    if result.best_frame is not None and args.save:
        import cv2

        cv2.imwrite(args.save, result.best_frame)
        print(_paint(f"saved {args.save}", DIM))
    return 0 if result.passed else 1


def cmd_info(args: argparse.Namespace) -> int:
    import verifyface as vf

    print(json.dumps(vf.Verifier(vault=args.vault).info(), indent=2, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verifyface",
        description=(
            "verifyface — simple, private, offline face verification.\n"
            "Developer: Kaustav Kanti Ray · https://github.com/iamkkronly/verifyface"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  verifyface enroll kaustav photo1.jpg photo2.jpg\n"
            "  verifyface verify kaustav selfie.jpg\n"
            "  verifyface identify group.jpg\n"
            "  verifyface serve\n"
        ),
    )
    parser.add_argument("--version", action="version", version=_meta.BANNER)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--vault", help="vault folder (default: %s)" % default_vault_path())
    common.add_argument(
        "--threshold",
        default=None,
        choices=[*THRESHOLD_PRESETS, "0.3", "0.33", "0.35", "0.4", "0.45", "0.48", "0.5"],
        help="strict | balanced | lenient | a number between 0 and 1",
    )

    p = sub.add_parser("enroll", parents=[common], help="register a person from photos")
    p.add_argument("identity", help="name of the person (any language)")
    p.add_argument("images", nargs="+", help="one or more photos")
    p.add_argument("--overwrite", action="store_true", help="replace the existing profile")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_enroll)

    p = sub.add_parser("verify", parents=[common], help="check a photo against a person")
    p.add_argument("identity")
    p.add_argument("image")
    p.add_argument("--pin", help="second factor, when one is set for this identity")
    p.add_argument("--ask-pin", action="store_true", help="prompt for the PIN (hidden input)")
    p.add_argument(
        "--liveness",
        default="off",
        choices=["off", "auto", "required"],
        help="passive anti-spoofing on the probe (rejects photos of screens/prints)",
    )
    p.add_argument(
        "--no-ambiguity-guard",
        dest="ambiguity_guard",
        action="store_false",
        help="allow a pass even when a lookalike is enrolled (not recommended)",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_verify, ambiguity_guard=True)

    p = sub.add_parser("pin", parents=[common], help="set a PIN (second factor) for a person")
    p.add_argument("identity")
    p.add_argument("--pin", help="the PIN itself (otherwise you are prompted)")
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser("clear-pin", parents=[common], help="remove the PIN of a person")
    p.add_argument("identity")
    p.set_defaults(func=cmd_clear_pin)

    p = sub.add_parser(
        "lookalikes", help="find twins/siblings that look too similar"
    )
    p.add_argument("--vault", help="vault folder")
    p.add_argument(
        "--threshold", type=float, default=0.5,
        help="similarity above which two enrolled people are considered lookalikes",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_lookalikes)

    p = sub.add_parser("identify", parents=[common], help="find who is in a photo")
    p.add_argument("image")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_identify)

    p = sub.add_parser("compare", parents=[common], help="compare two photos (stores nothing)")
    p.add_argument("image_a")
    p.add_argument("image_b")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("list", parents=[common], help="list enrolled people")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("delete", parents=[common], help="delete a person's profile")
    p.add_argument("identity")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("doctor", parents=[common], help="check the installation")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("download-models", help="fetch the ONNX models into the cache")
    p.add_argument("--dir", help="target folder")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_download_models)

    p = sub.add_parser("serve", help="start the browser app (upload + live camera)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--vault", default=None)
    p.add_argument("--open", action="store_true", help="open a browser window")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("demo", help="live camera demo on the desktop")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--actions", type=int, default=2)
    p.add_argument("--save", help="save the captured frame here")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("info", parents=[common], help="print engine information as JSON")
    p.set_defaults(func=cmd_info)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    _force_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except VerifyFaceError as exc:
        print(_bad(str(exc)), file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("\ncancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
