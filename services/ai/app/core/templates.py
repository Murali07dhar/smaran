"""Deterministic template fallback (offline / no key / unsafe model output).

Locales with templates: en, as, bn, ne. as/bn/ne are best-effort and UNVERIFIED by native
speakers. brx, mni, lus, kha, grt have no verified text templates, so they fall back to English
text (those locales are served by recorded voice packs in services/voice).
Placeholders use plain str.replace (never str.format) so context cannot inject format strings.
"""
from __future__ import annotations

import zlib

DEFAULT_TITLES: dict[str, dict[str, str]] = {
    "en": {"medicine": "your medicine", "hydration": "some water", "activity": "a little activity", "appointment": "your visit"},
    "bn": {"medicine": "আপনার ওষুধ", "hydration": "একটু জল", "activity": "হালকা কিছু কাজ", "appointment": "আপনার সাক্ষাৎ"},
    "as": {"medicine": "আপোনাৰ দৰৱ", "hydration": "অলপ পানী", "activity": "অলপ কাম", "appointment": "আপোনাৰ সাক্ষাৎ"},
    "ne": {"medicine": "तपाईंको औषधि", "hydration": "अलिकति पानी", "activity": "हल्का गतिविधि", "appointment": "तपाईंको भेट"},
}

REMINDER: dict[str, dict[str, list[str]]] = {
    "en": {
        "medicine": ["{name}, it is time for {title}. Take your time. We are right here with you.",
                     "{name}, a gentle reminder about {title}. Your family is thinking of you."],
        "hydration": ["{name}, a glass of water would be lovely right now.",
                      "{name}, shall we have {title} together?"],
        "activity": ["{name}, shall we enjoy {title} together?",
                     "{name}, how about {title} now? Whenever you feel ready."],
        "appointment": ["{name}, a gentle reminder that {title} is coming up. Your family will help you get ready.",
                        "{name}, {title} is coming up soon. We will go step by step."],
    },
    "bn": {
        "medicine": ["{name}, এখন {title} নেওয়ার সময়। ধীরে ধীরে করুন, আমরা আপনার পাশেই আছি।"],
        "hydration": ["{name}, এখন এক গ্লাস জল খেলে ভালো লাগবে।"],
        "activity": ["{name}, চলুন একসাথে {title} করি।"],
        "appointment": ["{name}, একটু মনে করিয়ে দিই: {title} আসছে। পরিবার আপনাকে তৈরি হতে সাহায্য করবে।"],
    },
    "as": {
        "medicine": ["{name}, এতিয়া {title} লোৱাৰ সময়। লাহে লাহে কৰক, আমি আপোনাৰ ওচৰতে আছো।"],
        "hydration": ["{name}, এতিয়া এগিলাচ পানী খালে ভাল লাগিব।"],
        "activity": ["{name}, আহক, একেলগে {title} কৰোঁ।"],
        "appointment": ["{name}, অলপ মনত পেলাই দিওঁ: {title} ওচৰ চাপি আহিছে। পৰিয়ালে আপোনাক সাজু হ'বলৈ সহায় কৰিব।"],
    },
    "ne": {
        "medicine": ["{name}, अब {title} लिने समय भयो। बिस्तारै गर्नुहोस्, हामी तपाईंसँगै छौं।"],
        "hydration": ["{name}, अहिले एक गिलास पानी पिउनुभयो भने राम्रो हुन्छ।"],
        "activity": ["{name}, आउनुहोस्, सँगै {title} गरौं।"],
        "appointment": ["{name}, सानो सम्झना: {title} नजिकै छ। परिवारले तयार हुन मद्दत गर्नेछ।"],
    },
}

GAME: dict[str, dict[str, list[str]]] = {
    "en": {
        "memory": ["Let us look at something nice together. Take all the time you like."],
        "attention": ["Let us find the special one together. There is no hurry."],
        "routine": ["Let us put the day in order, one step at a time."],
        "pattern_object": ["Let us look for what goes together."],
        "executive": ["Let us plan this together, step by step."],
    },
    "bn": {
        "memory": ["চলুন একসাথে সুন্দর কিছু দেখি। যতক্ষণ ইচ্ছে সময় নিন।"],
        "attention": ["চলুন বিশেষটি খুঁজে দেখি। কোনো তাড়া নেই।"],
        "routine": ["চলুন দিনের কাজগুলো এক এক করে সাজাই।"],
        "pattern_object": ["চলুন কোনটা কোনটার সাথে যায় দেখি।"],
        "executive": ["চলুন একসাথে ধাপে ধাপে পরিকল্পনা করি।"],
    },
    "as": {
        "memory": ["আহক, একেলগে ভাল কিবা এটা চাওঁ। যিমান ইচ্ছা সময় লওক।"],
        "attention": ["আহক, বিশেষটো বিচাৰি চাওঁ। কোনো ততা নাই।"],
        "routine": ["আহক, দিনটোৰ কামবোৰ এটা এটাকৈ সজাওঁ।"],
        "pattern_object": ["আহক, কোনটো কোনটোৰ লগত খাপ খায় চাওঁ।"],
        "executive": ["আহক, একেলগে খোজে খোজে পৰিকল্পনা কৰোঁ।"],
    },
    "ne": {
        "memory": ["आउनुहोस्, सँगै राम्रो कुरा हेरौं। जति समय चाहिन्छ लिनुहोस्।"],
        "attention": ["आउनुहोस्, विशेषलाई खोजौं। कुनै हतार छैन।"],
        "routine": ["आउनुहोस्, दिनका कामलाई एकएक गरी मिलाऔं।"],
        "pattern_object": ["आउनुहोस्, कुन कुनसँग मिल्छ हेरौं।"],
        "executive": ["आउनुहोस्, सँगै चरणबद्ध योजना बनाऔं।"],
    },
}

TEMPLATE_LOCALES = frozenset(REMINDER)


def _pick(options: list[str], seed: str) -> str:
    return options[zlib.crc32(seed.encode()) % len(options)]


def finalize(text: str, name: str, title: str) -> str:
    """Substitute {name}/{title}; with no name drop the address cleanly."""
    if name:
        text = text.replace("{name}", name)
    else:
        text = text.replace("{name}, ", "").replace("{name}", "")
    text = text.replace("{title}", title).strip()
    return text[:1].upper() + text[1:] if text else text


def render(kind: str, locale: str, ctx: dict[str, str]) -> str:
    loc = locale if locale in TEMPLATE_LOCALES else "en"
    name = ctx.get("name", "")
    if kind == "reminder_phrase":
        cat = ctx.get("category", "")
        cat = cat if cat in REMINDER["en"] else "activity"
        title = ctx.get("title") or DEFAULT_TITLES[loc][cat]
        tpl = _pick(REMINDER[loc][cat], f"{cat}|{name}|{ctx.get('time', '')}")
        return finalize(tpl, name, title)
    domain = ctx.get("domain", "")
    domain = domain if domain in GAME["en"] else "memory"
    tpl = _pick(GAME[loc][domain], f"{domain}|{name}")
    return finalize(tpl, name, "")
