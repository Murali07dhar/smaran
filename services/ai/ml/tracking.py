"""MLflow tracking with a graceful JSON fallback when mlflow is not installed.

    with tracked_run("smaran-ai", "fer-cnn", params={"epochs": 20}) as run:
        run.log_metrics({"val_acc": 0.61})
        run.log_artifact("ml/models/fer_cnn.onnx")

Set MLFLOW_TRACKING_URI to log to a server; otherwise MLflow uses ./mlruns.
Fallback runs are written to ./mlruns_fallback/<experiment>-<run>.json.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class _JsonRun:
    def __init__(self, experiment: str, name: str, params: dict | None) -> None:
        self.path = Path("mlruns_fallback") / f"{experiment}-{name}.json"
        self.data: dict = {"experiment": experiment, "run": name, "params": params or {}, "metrics": [], "artifacts": []}

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        self.data["metrics"].append({"step": step, "t": time.time(), **metrics})

    def log_artifact(self, path: str) -> None:
        self.data["artifacts"].append(str(path))

    def close(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, default=str))


class _MlflowRun:
    def __init__(self, mlflow) -> None:  # noqa: ANN001
        self.mlflow = mlflow

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        self.mlflow.log_metrics(metrics, step=step)

    def log_artifact(self, path: str) -> None:
        if Path(path).exists():
            self.mlflow.log_artifact(str(path))


@contextmanager
def tracked_run(experiment: str, name: str, params: dict | None = None) -> Iterator[object]:
    try:
        import mlflow  # type: ignore
    except ImportError:
        run = _JsonRun(experiment, name, params)
        try:
            yield run
        finally:
            run.close()
        return
    uri = os.getenv("MLFLOW_TRACKING_URI")
    if uri:
        mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=name):
        if params:
            mlflow.log_params({k: str(v)[:250] for k, v in params.items()})
        yield _MlflowRun(mlflow)
