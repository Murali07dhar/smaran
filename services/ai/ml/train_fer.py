"""Train a small FER-2013 CNN (PyTorch) and export it to ONNX for onnxruntime-web.

Needs: pip install torch pandas numpy onnx onnxruntime mlflow
Data:  fer2013.csv (Kaggle "Challenges in Representation Learning: FER", columns emotion,pixels,Usage).
       Download it yourself and respect its licence. It is NOT bundled here.

    python -m ml.train_fer --csv path/to/fer2013.csv --epochs 25
    python -m ml.train_fer --smoke            # random data, only checks the train/export pipeline

I/O matches ml/make_smoke_onnx.py: input [N,1,48,48] float32 (pixel/255) -> logits, probs [N,7].
Class order is app.core.va_mapping.FER_CLASSES. Bias caveat: FER-2013 is mostly younger,
non-Indian, acted/web faces. Report subgroup accuracy before any real use.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from app.core.va_mapping import FER_CLASSES
from ml.make_smoke_onnx import meta
from ml.tracking import tracked_run

OUT_DIR = Path(__file__).parent / "models"


def load_fer_csv(path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    import pandas as pd

    df = pd.read_csv(path)
    x = np.stack([np.fromstring(p, dtype=np.float32, sep=" ").reshape(48, 48) for p in df["pixels"]]) / 255.0
    y = df["emotion"].to_numpy(dtype=np.int64)
    tr, va = (df["Usage"] == "Training").to_numpy(), (df["Usage"] == "PublicTest").to_numpy()
    return x[tr][:, None], y[tr], x[va][:, None], y[va]


def smoke_data(n: int = 256) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    x = rng.random((n, 1, 48, 48), dtype=np.float32)
    y = rng.integers(0, 7, n)
    return x[: n // 2], y[: n // 2], x[n // 2:], y[n // 2:]


def build_model():  # noqa: ANN201
    import torch.nn as nn

    def block(i: int, o: int) -> nn.Sequential:
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(), nn.MaxPool2d(2))

    return nn.Sequential(block(1, 32), block(32, 64), block(64, 128), nn.AdaptiveAvgPool2d(1), nn.Flatten(),
                         nn.Dropout(0.3), nn.Linear(128, len(FER_CLASSES)))


def main() -> None:
    import torch
    import torch.nn as nn

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv")
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=str(OUT_DIR / "fer_cnn.onnx"))
    a = ap.parse_args()
    if not a.smoke and not a.csv:
        ap.error("--csv is required unless --smoke")

    torch.manual_seed(0)
    xtr, ytr, xva, yva = smoke_data() if a.smoke else load_fer_csv(a.csv)
    model = build_model()
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    xtr_t, ytr_t = torch.from_numpy(xtr), torch.from_numpy(ytr)
    xva_t, yva_t = torch.from_numpy(xva), torch.from_numpy(yva)
    epochs = 1 if a.smoke else a.epochs

    with tracked_run("smaran-ai", "fer-cnn-smoke" if a.smoke else "fer-cnn",
                     {"epochs": epochs, "batch": a.batch, "lr": a.lr, "smoke": a.smoke}) as run:
        for ep in range(epochs):
            model.train()
            perm = torch.randperm(len(xtr_t))
            for i in range(0, len(perm), a.batch):
                idx = perm[i:i + a.batch]
                xb = xtr_t[idx]
                if torch.rand(1).item() < 0.5:  # cheap augmentation: horizontal flip
                    xb = torch.flip(xb, dims=[3])
                opt.zero_grad()
                loss = loss_fn(model(xb), ytr_t[idx])
                loss.backward()
                opt.step()
            model.eval()
            with torch.no_grad():
                acc = (model(xva_t).argmax(1) == yva_t).float().mean().item()
            run.log_metrics({"val_acc": acc, "train_loss": float(loss)}, step=ep)
            print(f"epoch {ep + 1}/{epochs} val_acc={acc:.3f}")

        class Export(nn.Module):
            def __init__(self, m: nn.Module) -> None:
                super().__init__()
                self.m = m

            def forward(self, x):  # noqa: ANN001, ANN201
                logits = self.m(x)
                return logits, torch.softmax(logits, dim=1)

        model.eval()
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        torch.onnx.export(Export(model), torch.zeros(1, 1, 48, 48), str(out), input_names=["input"],
                          output_names=["logits", "probs"], opset_version=13,
                          dynamic_axes={"input": {0: "N"}, "logits": {0: "N"}, "probs": {0: "N"}})
        info = meta(trained=not a.smoke, version="smoke" if a.smoke else "1.0")
        info["metrics"] = {"val_acc_public_test": acc}
        out.with_suffix(".meta.json").write_text(json.dumps(info, indent=2, ensure_ascii=False))
        run.log_artifact(str(out))
        print("exported", out)


if __name__ == "__main__":
    main()
