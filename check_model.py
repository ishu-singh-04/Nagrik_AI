import google.generativeai as genai
import os
from dotenv import load_dotenv

# API Key load karega
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

print("🚨 GOOGLE API KE AVAILABLE MODELS 🚨\n")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)