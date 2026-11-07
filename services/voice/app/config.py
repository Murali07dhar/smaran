import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # "auto": use real model if importable + weights present, else fall back. "off": never load models (CI, laptops).
    models_mode: str = os.getenv("VOICE_MODELS_MODE", "auto")
    model_dir: str = os.getenv("VOICE_MODEL_DIR", "/models")
    device: str = os.getenv("VOICE_DEVICE", "cpu")  # cpu | cuda
    max_audio_bytes: int = int(os.getenv("VOICE_MAX_AUDIO_BYTES", str(5 * 1024 * 1024)))
    max_tts_chars: int = int(os.getenv("VOICE_MAX_TTS_CHARS", "400"))
    jwt_public_key: str = os.getenv("JWT_PUBLIC_KEY", "")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    require_auth: bool = os.getenv("VOICE_REQUIRE_AUTH", "true").lower() == "true"
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174")


settings = Settings()

# Locale -> model language code. brx/mni are supported by IndicConformer/IndicTrans2 in some releases
# (verify against the checkpoint you download). lus/kha/grt have NO ASR/TTS: use recorded voice packs.
ASR_LANG = {"as": "as", "bn": "bn", "ne": "ne", "brx": "brx", "mni": "mni", "en": "en"}
TTS_LANG = {"as": "as", "bn": "bn", "ne": "ne", "brx": "brx", "mni": "mni", "en": "en"}
PACK_ONLY = {"lus", "kha", "grt"}
