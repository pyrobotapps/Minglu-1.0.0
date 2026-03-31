import aiohttp
from config import AZURE_KEY, AZURE_ENDPOINT, AZURE_REGION

LANG_CODES = {
    "zh": "zh-Hans",
    "ja": "ja",
    "ko": "ko",
    "th": "th",
    "ru": "ru",
}


async def translate_text(session: aiohttp.ClientSession, text: str, target_lang: str) -> str:
    if not text or not text.strip():
        return "N/A"

    if not AZURE_KEY or not AZURE_ENDPOINT or not AZURE_REGION:
        return text

    url = f"{AZURE_ENDPOINT}/translate?api-version=3.0&to={target_lang}"
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_KEY,
        "Ocp-Apim-Subscription-Region": AZURE_REGION,
        "Content-Type": "application/json",
    }
    body = [{"text": text}]

    try:
        async with session.post(url, headers=headers, json=body, timeout=20) as resp:
            data = await resp.json()
            return data[0]["translations"][0]["text"]
    except Exception:
        return text