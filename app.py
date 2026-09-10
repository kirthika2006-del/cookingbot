import json
import os
import re

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from google import genai
from google.genai import types

from chatbot_config import MODEL_NAME, SYSTEM_PROMPT

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY) if API_KEY else None

COOKING_TERMS = {
    "cook", "cooking", "recipe", "recipes", "food", "dish", "dishes",
    "ingredient", "ingredients", "kitchen", "bake", "baking", "fry", "fried",
    "boil", "boiled", "steam", "steamed", "roast", "grill", "grilled",
    "saute", "sauté", "curry", "soup", "salad", "dessert", "cake", "bread",
    "rice", "pasta", "pizza", "noodles", "chicken", "fish", "meat",
    "vegetable", "vegan", "vegetarian", "breakfast", "lunch", "dinner",
    "snack", "spice", "spices", "masala", "sauce", "batter", "dough",
    "oven", "pan", "pot", "air fryer", "pressure cooker", "meal", "meals",
    "nutrition", "calories", "substitute", "substitution", "cooking time",
    "temperature", "how to make", "how do i make"
}

def is_cooking_related(text: str) -> bool:
    normalized = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return any(term in normalized for term in COOKING_TERMS)

def build_history(raw_history):
    if not isinstance(raw_history, list):
        return []
    history = []
    for item in raw_history[-12:]:
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), item.get("content")
        if role in {"user", "model"} and isinstance(content, str) and content.strip():
            history.append(types.Content(role=role, parts=[types.Part.from_text(text=content[:6000])]))
    return history

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"status": "ok", "model": MODEL_NAME, "configured": bool(API_KEY)})

@app.post("/chat")
def chat():
    if not API_KEY or client is None:
        return jsonify({"error": "CookingBot AI is not configured. Please provide the Gemini API key."}), 500

    message = (request.form.get("message") or "").strip()
    image_file = request.files.get("image")
    has_image = bool(image_file and image_file.filename)

    if not message and not has_image:
        return jsonify({"error": "Please enter a cooking question or attach a food image."}), 400

    if message and not is_cooking_related(message) and not has_image:
        return jsonify({"reply": "I’m CookingBot AI 🍳 — I’m designed specifically for cooking, recipes, ingredients, kitchen techniques, food preparation and meal ideas. Ask me something about cooking and I’ll help!"})

    try:
        history = build_history(json.loads(request.form.get("history", "[]")))
    except (TypeError, ValueError, json.JSONDecodeError):
        history = []

    parts = [types.Part.from_text(text=message or "Analyze the attached food/cooking image and help me with it.")]
    if has_image:
        parts.append(types.Part.from_bytes(data=image_file.read(), mime_type=image_file.mimetype or "image/jpeg"))

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=history + [types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.65,
                max_output_tokens=1400,
            ),
        )
        reply = (response.text or "").strip() or "I couldn't generate a cooking response right now. Please try again."
        return jsonify({"reply": reply})
    except Exception:
        app.logger.exception("Gemini request failed")
        return jsonify({"error": "I couldn't process that request right now. Please check the Gemini API configuration and try again."}), 502

@app.errorhandler(413)
def file_too_large(_):
    return jsonify({"error": "That image is too large. Please upload an image smaller than 8 MB."}), 413

if __name__ == "__main__":
    app.run(debug=True)
