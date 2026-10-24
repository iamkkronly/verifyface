# Security policy

Developer: Kaustav Kanti Ray

## Reporting a vulnerability

**Please do not open a public issue.** Email
<iamkkronly@users.noreply.github.com> with:

1. a description of the problem and its impact,
2. steps to reproduce (a synthetic image is fine — never send a real person's
   photo),
3. the verifyface version and your OS / Python version,
4. any suggested fix.

You will get an acknowledgement within 72 hours and a resolution target of
30 days for critical issues. Credit will be given in `CHANGELOG.md` unless you
prefer to stay anonymous.

## Supported versions

| Version | Supported |
|---|---|
| 1.x | ✅ |

## Scope

In scope:

- template forgery or silent acceptance of a modified template,
- path traversal or file overwrite through identity names,
- crashes or arbitrary code execution from a malicious image,
- bypassing the liveness checks with a **still image or replayed video**,
- leaking image data into the vault, logs or network.

Out of scope (documented limitations):

- 3-D masks, silicone replicas and real-time deepfakes,
- physical coercion of a person standing in front of the camera,
- an attacker who already controls the machine, the vault key and the process,
- the demo web server being exposed to the public internet without a reverse
  proxy or authentication (it is a demo, not a hardened identity provider).

## Hardening guidance

See [docs/security.md](docs/security.md) for the threat model and the
deployment checklist (encrypted templates, `VERIFYFACE_KEY` from a secret
manager, strict threshold, mandatory liveness, second factor for high-value
actions).
