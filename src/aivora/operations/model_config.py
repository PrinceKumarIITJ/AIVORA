from dataclasses import replace

from sqlalchemy import select

from .connectors import decrypt
from .models import ModelProfile


def resolve_settings(db, settings, org_id):
    profile = db.scalar(select(ModelProfile).where(ModelProfile.org_id == org_id))
    if not profile:
        return settings, {
            "provider": settings.provider,
            "model": settings.model,
            "profile_id": "",
            "revision": 0,
        }
    key = decrypt(settings, profile.secret_ciphertext)
    configured = replace(
        settings,
        provider=profile.provider,
        model=profile.model,
        groq_key=key if profile.provider == "groq" else "",
        google_key=key if profile.provider == "gemini" else "",
    )
    return configured, {
        "provider": profile.provider,
        "model": profile.model,
        "profile_id": profile.id,
        "revision": profile.revision,
    }
