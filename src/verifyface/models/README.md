# Bundled models

Developer: Kaustav Kanti Ray — https://github.com/iamkkronly/verifyface

| File | Purpose | Source | License |
|------|---------|--------|---------|
| `face_detection_yunet_2023mar_int8bq.onnx` | YuNet face detector (5 landmarks) | [opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | Apache-2.0 (OpenCV Zoo) / MIT (libfacedetection) |
| `face_recognition_sface_2021dec_int8bq.onnx` | SFace face recognizer (128-d) | [opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) | Apache-2.0 (OpenCV Zoo) |

The int8 block-quantized builds are ~3.5x smaller than the fp32 files with a
measured accuracy difference of <0.001 on the calibration set.

SHA-256:

```
49f000ec501fef24739071fc7e68267d32209045b6822c0c72dce1da25726f10  face_detection_yunet_2023mar_int8bq.onnx
fb143eea07838aa532d1c95df5f69899974ea0140e1fba05e94204be13ed74ee  face_recognition_sface_2021dec_int8bq.onnx
```

The library verifies both files against these digests before loading them
(see `verifyface.engine.MODEL_SHA256`). If a bundled file is ever missing, the
same files can be fetched with `verifyface download-models`.
