from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import models
from .auth import current_user
from .config import ASR_LANG, PACK_ONLY, TTS_LANG, settings

app = FastAPI(title="SMARAN voice service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

PROBLEM = "application/problem+json"


def problem(status: int, title: str, detail: str, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail, **extra},
    )


@app.exception_handler(HTTPException)
async def _http(_: Request, exc: HTTPException):
    return problem(exc.status_code, str(exc.detail), str(exc.detail))


@app.exception_handler(RequestValidationError)
async def _val(_: Request, exc: RequestValidationError):
    return problem(422, "Validation error", "Invalid request", errors=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()])


@app.exception_handler(models.ModelUnavailable)
async def _mu(_: Request, exc: models.ModelUnavailable):
    # 503 + machine-readable fallback so the VoiceAPI client switches to on-device speech.
    fb = {
        "asr": "browser_web_speech_api_or_tap_buttons",
        "tts": "browser_speech_synthesis_or_voice_pack",
        "lid": "script_heuristic",
    }.get(exc.what, "none")
    return problem(503, f"{exc.what} model unavailable", exc.reason, fallback=fb)


@app.get("/voice/health")
def health():
    return {"status": "ok", "models_mode": settings.models_mode, "device": settings.device}


@app.get("/voice/capabilities")
def capabilities(_: dict = Depends(current_user)):
    return {
        "asr_locales": sorted(ASR_LANG),
        "tts_locales": sorted(TTS_LANG),
        "voice_pack_only_locales": sorted(PACK_ONLY),
        "note": "Listed locales are what the code can route; actual availability depends on installed checkpoints (503 + fallback otherwise).",
    }


@app.post("/voice/asr")
async def asr(request: Request, locale: str = Query(...), _: dict = Depends(current_user)):
    if locale in PACK_ONLY:
        return problem(422, "No ASR for locale", f"'{locale}' has no ASR model; use buttons.", fallback="tap_buttons")
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio body")
    if len(audio) > settings.max_audio_bytes:
        raise HTTPException(status_code=413, detail="Audio too large")
    transcript = models.transcribe(audio, locale)
    return {"transcript": transcript, "locale": locale, "engine": "indicconformer"}


class LidIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.post("/voice/lid")
def lid(body: LidIn, _: dict = Depends(current_user)):
    return models.detect_language(body.text)


class TtsIn(BaseModel):
    text: str = Field(min_length=1)
    locale: str


@app.post("/voice/tts")
def tts(body: TtsIn, _: dict = Depends(current_user)):
    if len(body.text) > settings.max_tts_chars:
        raise HTTPException(status_code=413, detail=f"Text longer than {settings.max_tts_chars} chars")
    if body.locale in PACK_ONLY:
        return problem(422, "No TTS for locale", f"'{body.locale}' uses recorded voice packs.", fallback="voice_pack")
    audio = models.synthesize(body.text, body.locale)
    return Response(content=audio, media_type="audio/wav")
