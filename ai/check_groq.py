import os
import requests
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("GROQ_API_KEY")

if not key:
    print("🚨 No GROQ_API_KEY found in .env")
    exit()

url = "https://api.groq.com/openai/v1/models"
headers = {"Authorization": f"Bearer {key}"}

print("Checking Groq API key...")

try:
    r = requests.get(url, headers=headers, timeout=30)
    print("Status:", r.status_code)

    if r.status_code != 200:
        print("🚨 Groq API error:")
        print(r.text[:1000])
        exit()

    models = [m["id"] for m in r.json().get("data", [])]

    print("\nAvailable models for your account:")
    for m in models:
        print("-", m)

    preferred = [
        m for m in models
        if "llama" in m and ("70b" in m or "8b" in m)
    ]

    chosen = preferred[0] if preferred else (models[0] if models else None)

    if chosen:
        print("\nAdd this line to your .env file:")
        print(f"GROQ_MODEL={chosen}")
    else:
        print("🚨 Your Groq account has no available models.")

except Exception as e:
    print("🚨 Network error while contacting Groq:")
    print(e)