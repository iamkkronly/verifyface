# Authors

## Creator and lead developer

**Kaustav Kanti Ray**
GitHub: [@iamkkronly](https://github.com/iamkkronly)
Project: <https://github.com/iamkkronly/verifyface>

Designed and implemented the library: architecture, the verification pipeline,
the encrypted template vault, liveness/challenge–response, the CLI, the
zero-dependency browser app, the framework integrations, the documentation and
the test suite.

## Third-party credits

| Component | Author / project | License |
|---|---|---|
| YuNet face detector | Shiqi Yu et al. — via [OpenCV Zoo](https://github.com/opencv/opencv_zoo) | Apache-2.0 / MIT |
| SFace face recogniser | Yaoyao Zhong et al. — via [OpenCV Zoo](https://github.com/opencv/opencv_zoo) | Apache-2.0 |
| OpenCV | [opencv.org](https://opencv.org) | Apache-2.0 |
| NumPy | [numpy.org](https://numpy.org) | BSD-3-Clause |
| Pillow | [python-pillow.org](https://python-pillow.org) | HPND |
| Test photographs | Wikimedia Commons contributors | Public domain / CC BY / CC BY-SA (see `tests/fixtures/CREDITS.md`) |

The int8 block-quantised model files were produced by the OpenCV Zoo
`block_quantize.py` tool from the original fp32 weights.

---

Every source file in this repository carries the line
`Developer: Kaustav Kanti Ray`, as requested by the project owner.
