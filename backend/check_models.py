"""Day 4: find which Gemini Flash models your project can use.

Usage: python backend/check_models.py
Then put the newest one that says OK into .env as GEMINI_MODEL.
"""
import os

from google import genai

PROJECT = os.environ["PROJECT_ID"]
LOCATION = os.environ.get("GEMINI_LOCATION", "global")
client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

print("Gemini Flash models listed for your project:")
try:
    names = sorted({m.name.rsplit("/", 1)[-1] for m in client.models.list(config={"query_base": True})
                    if "flash" in (m.name or "")})
    for n in names:
        print("  ", n)
except Exception as e:  # listing is not available everywhere; the test below still works
    names = []
    print("   (could not list models:", str(e)[:120], ")")

candidates = [n for n in names if "image" not in n and "tts" not in n and "live" not in n] or [
    "gemini-3.5-flash", "gemini-3-flash", "gemini-3-flash-preview", "gemini-2.5-flash"]

print("\nTesting each model with a tiny request:")
for model in candidates:
    try:
        r = client.models.generate_content(model=model, contents="Reply with the single word OK")
        print(f"   OK    {model}  -> {(r.text or '').strip()[:20]}")
    except Exception as e:
        print(f"   FAIL  {model}  ({str(e)[:90]})")

print("\nPick the newest model marked OK that is NOT 'preview', and run:")
print("   echo 'export GEMINI_MODEL=<model-name>' >> .env && source .env")