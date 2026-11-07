"""Fine-tune Wav2Vec2 for speech emotion on RAVDESS (8 classes) and optionally export to ONNX.

Needs: pip install torch torchaudio transformers mlflow onnx
Data:  RAVDESS speech audio (Zenodo 1188976, CC BY-NC-SA 4.0: NON-COMMERCIAL licence, check it
       fits your deployment). Folder layout: <root>/Actor_01/03-01-05-01-01-01-01.wav ...
       Filename field 3 is the emotion code: 01 neutral, 02 calm, 03 happy, 04 sad, 05 angry,
       06 fearful, 07 disgust, 08 surprised.

    python -m ml.train_speech --root path/to/RAVDESS --epochs 5 [--export-onnx]

ONNX feasibility: wav2vec2-base is ~95M parameters (~380 MB fp32). Exporting works with
torch.onnx.export, but it is too large for in-browser use on entry-level Android, so this model
is intended for SERVER-SIDE use (services/ai or services/voice). A distilled/quantised model is
future work. RAVDESS is acted North-American English: it does NOT represent Assamese or other
NER speakers or elderly voices. Treat outputs as weak signals; keep emotion optional.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from app.core.va_mapping import RAVDESS_CLASSES
from ml.tracking import tracked_run

OUT_DIR = Path(__file__).parent / "models"
CODE_TO_IDX = {f"{i + 1:02d}": i for i in range(8)}  # RAVDESS code order == RAVDESS_CLASSES order
SR = 16000
MAX_SECONDS = 4


def list_files(root: str) -> list[tuple[Path, int]]:
    items = []
    for p in sorted(Path(root).rglob("*.wav")):
        parts = p.stem.split("-")
        if len(parts) >= 3 and parts[2] in CODE_TO_IDX:
            items.append((p, CODE_TO_IDX[parts[2]]))
    return items


def split_by_actor(items: list[tuple[Path, int]], val_actors: int = 4) -> tuple[list, list]:
    actors = sorted({p.parent.name for p, _ in items})
    val = set(actors[-val_actors:])  # speaker-independent split avoids leakage
    return [i for i in items if i[0].parent.name not in val], [i for i in items if i[0].parent.name in val]


def main() -> None:
    import torch
    import torchaudio
    from transformers import Wav2Vec2ForSequenceClassification

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    ap.add_argument("--base", default="facebook/wav2vec2-base")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--export-onnx", action="store_true")
    a = ap.parse_args()

    items = list_files(a.root)
    if not items:
        raise SystemExit(f"no RAVDESS wav files found under {a.root}")
    train, val = split_by_actor(items)
    random.Random(0).shuffle(train)

    def load(path: Path) -> torch.Tensor:
        wav, sr = torchaudio.load(str(path))
        wav = torchaudio.functional.resample(wav.mean(0), sr, SR)[: SR * MAX_SECONDS]
        wav = (wav - wav.mean()) / (wav.std() + 1e-7)
        return torch.nn.functional.pad(wav, (0, SR * MAX_SECONDS - len(wav)))

    model = Wav2Vec2ForSequenceClassification.from_pretrained(a.base, num_labels=len(RAVDESS_CLASSES))
    model.freeze_feature_encoder()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr)

    def batches(rows: list, bs: int):  # noqa: ANN202
        for i in range(0, len(rows), bs):
            chunk = rows[i:i + bs]
            yield torch.stack([load(p) for p, _ in chunk]), torch.tensor([y for _, y in chunk])

    with tracked_run("smaran-ai", "speech-emotion-wav2vec2", {"epochs": a.epochs, "base": a.base, "lr": a.lr}) as run:
        for ep in range(a.epochs):
            model.train()
            for xb, yb in batches(train, a.batch):
                opt.zero_grad()
                model(xb, labels=yb).loss.backward()
                opt.step()
            model.eval()
            correct = 0
            with torch.no_grad():
                for xb, yb in batches(val, a.batch):
                    correct += (model(xb).logits.argmax(-1) == yb).sum().item()
            acc = correct / max(1, len(val))
            run.log_metrics({"val_acc_unseen_actors": acc}, step=ep)
            print(f"epoch {ep + 1}/{a.epochs} val_acc={acc:.3f}")

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(OUT_DIR / "speech_emotion_wav2vec2")
        (OUT_DIR / "speech_emotion.meta.json").write_text(json.dumps(
            {"classes": RAVDESS_CLASSES, "sample_rate": SR, "max_seconds": MAX_SECONDS,
             "val_acc_unseen_actors": acc, "licence_note": "RAVDESS is CC BY-NC-SA 4.0",
             "caveat": "Acted North-American English; not validated on elderly or NER speakers."}, indent=2))
        if a.export_onnx:
            model.config.return_dict = False
            onnx_path = OUT_DIR / "speech_emotion_wav2vec2.onnx"
            torch.onnx.export(model, torch.zeros(1, SR * MAX_SECONDS), str(onnx_path), input_names=["audio"],
                              output_names=["logits"], opset_version=14, dynamic_axes={"audio": {0: "N"}, "logits": {0: "N"}})
            run.log_artifact(str(onnx_path))
            print("exported", onnx_path, "(server-side use; too large for the browser)")


if __name__ == "__main__":
    main()
