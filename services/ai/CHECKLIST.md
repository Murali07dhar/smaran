# SMARAN AI Engine: CHECKLIST (resume from here on "continue")

Legend: [x] done, [ ] remaining

## P1: Golden-path core
- [x] requirements.txt, .env.example, Dockerfile
- [x] app/config, clock, problem (RFC 7807), schemas, store
- [x] POST /ai/triggers/update (Beta + decay + River re-validation)
- [x] POST /ai/difficulty/next (River)
- [x] POST /ai/severity/estimate (rules + disclaimer)
- [x] POST /ai/emotion/fuse (fusion + calibration)
- [x] POST /ai/content/generate (Gemini + template fallback)
- [x] app/main.py, app/asgi.py

## P2: Remaining features
- [x] ml/synthetic.py generator
- [x] ml/tracking.py (MLflow wrapper)
- [x] FER CNN training script + ONNX export (ml/train_fer.py) [script written, NEVER RUN; no torch/dataset]
- [x] Smoke ONNX artifact (UNTRAINED placeholder; real model still to train)
- [x] Speech emotion training script (never run; no model/ONNX produced)
- [x] DeepFace server fallback module
- [x] scripts/mock_client.py
- [x] scripts/demo_trigger_decay.py (+ csv/png)
- [x] ml/evaluate_synthetic.py
- [x] openapi.json export

## P3: Tests, CI, docs
- [x] pytest suite (all endpoints + contract + onnx)
- [x] ci/ai-ci.yml
- [x] model_cards/*
- [x] HANDOFF.md
- [x] zip

## Still open (see HANDOFF.md section 8)
- [ ] Train real FER model + subgroup evaluation; replace smoke ONNX
- [ ] Train/export speech model (server-side)
- [ ] Docker build and CI never executed
- [ ] Gemini never called against the live API
- [ ] CCR-AI-1..5 decisions from the Integrator / Claude 1
- [ ] Native-speaker review of as/bn/ne text; Bodo/Meitei content
- [ ] Encrypted-at-rest state, multi-worker
