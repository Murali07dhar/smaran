"""Builds an UNTRAINED FER-shaped ONNX CNN using only numpy + onnx.

Purpose: let apps/patient-web wire onnxruntime-web NOW with the exact I/O contract of the
real model. Weights are random, so its predictions are meaningless. Replace with the output of
ml/train_fer.py (same input/output names and shapes).

    python -m ml.make_smoke_onnx          # writes ml/models/fer_cnn_smoke.onnx + .meta.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

from app.core.va_mapping import FER_CLASSES, FER_VA

OUT_DIR = Path(__file__).parent / "models"


def build(seed: int = 0) -> onnx.ModelProto:
    rng = np.random.default_rng(seed)

    def w(*shape: int) -> np.ndarray:
        fan_in = int(np.prod(shape[1:])) if len(shape) > 1 else shape[0]
        return (rng.standard_normal(shape) * np.sqrt(2.0 / fan_in)).astype(np.float32)

    inits = [
        numpy_helper.from_array(w(8, 1, 3, 3), "conv1_w"), numpy_helper.from_array(np.zeros(8, np.float32), "conv1_b"),
        numpy_helper.from_array(w(16, 8, 3, 3), "conv2_w"), numpy_helper.from_array(np.zeros(16, np.float32), "conv2_b"),
        numpy_helper.from_array(w(7, 16), "fc_w"), numpy_helper.from_array(np.zeros(7, np.float32), "fc_b"),
    ]
    nodes = [
        helper.make_node("Conv", ["input", "conv1_w", "conv1_b"], ["c1"], pads=[1, 1, 1, 1], kernel_shape=[3, 3]),
        helper.make_node("Relu", ["c1"], ["r1"]),
        helper.make_node("MaxPool", ["r1"], ["p1"], kernel_shape=[2, 2], strides=[2, 2]),
        helper.make_node("Conv", ["p1", "conv2_w", "conv2_b"], ["c2"], pads=[1, 1, 1, 1], kernel_shape=[3, 3]),
        helper.make_node("Relu", ["c2"], ["r2"]),
        helper.make_node("MaxPool", ["r2"], ["p2"], kernel_shape=[2, 2], strides=[2, 2]),
        helper.make_node("GlobalAveragePool", ["p2"], ["gap"]),
        helper.make_node("Flatten", ["gap"], ["flat"], axis=1),
        helper.make_node("Gemm", ["flat", "fc_w", "fc_b"], ["logits"], transB=1),
        helper.make_node("Softmax", ["logits"], ["probs"], axis=1),
    ]
    graph = helper.make_graph(
        nodes, "smaran_fer_cnn_smoke",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, ["N", 1, 48, 48])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["N", 7]),
         helper.make_tensor_value_info("probs", TensorProto.FLOAT, ["N", 7])],
        initializer=inits,
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], producer_name="smaran-ai")
    model.ir_version = 8  # broad onnxruntime-web compatibility
    onnx.checker.check_model(model)
    return model


def meta(trained: bool, version: str) -> dict:
    return {
        "name": "smaran-fer-cnn", "version": version, "trained": trained,
        "warning": None if trained else "UNTRAINED PLACEHOLDER: random weights, predictions are meaningless.",
        "input": {"name": "input", "shape": ["N", 1, 48, 48], "dtype": "float32",
                  "preprocess": "grayscale, face crop, resize 48x48, pixel/255.0, no mean subtraction"},
        "outputs": {"logits": ["N", 7], "probs": ["N", 7]},
        "classes": FER_CLASSES,
        "class_valence_arousal": {k: list(v) for k, v in FER_VA.items()},
        "face_reading_from_probs": "valence=sum(p_k*v_k); arousal=sum(p_k*a_k); conf=max(p_k)  -> POST /ai/emotion/fuse face",
        "training_data_caveat": "FER-2013 is not representative of elderly faces or North-East India. Keep capture optional; caregiver confirms.",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    onnx.save(build(), str(OUT_DIR / "fer_cnn_smoke.onnx"))
    (OUT_DIR / "fer_cnn_smoke.meta.json").write_text(json.dumps(meta(False, "0.0-smoke"), indent=2, ensure_ascii=False))
    print("wrote", OUT_DIR / "fer_cnn_smoke.onnx")


if __name__ == "__main__":
    main()
