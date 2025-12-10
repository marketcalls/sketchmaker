#!/usr/bin/env python3
"""
Add new Groq models to existing database and set default
Run: uv run add_groq_models.py
"""

import sqlite3
import os

# Database path
DB_PATHS = [
    os.path.join(os.path.dirname(__file__), 'instance', 'sketchmaker.db'),
    os.path.join(os.path.dirname(__file__), 'sketchmaker.db'),
]

DB_PATH = None
for path in DB_PATHS:
    if os.path.exists(path):
        DB_PATH = path
        break

if not DB_PATH:
    print("Error: Database not found")
    exit(1)

print(f"Database: {DB_PATH}")
print("=" * 50)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get Groq provider ID
cursor.execute("SELECT id FROM api_provider WHERE name = 'Groq'")
row = cursor.fetchone()
if not row:
    print("Error: Groq provider not found")
    exit(1)

groq_id = row[0]
print(f"Groq provider ID: {groq_id}")

# New models to add
new_models = [
    {
        "name": "qwen/qwen3-32b",
        "display_name": "Qwen 3 32B",
        "description": "Alibaba Qwen 3 with exceptional text generation",
        "is_latest": True,
        "sort_order": 10
    },
    {
        "name": "moonshotai/kimi-k2-instruct-0905",
        "display_name": "Kimi K2 Instruct (Moonshot)",
        "description": "1T parameter MoE with 256K context",
        "is_latest": True,
        "sort_order": 11
    },
    {
        "name": "openai/gpt-oss-120b",
        "display_name": "GPT-OSS 120B",
        "description": "OpenAI open-weight 120B reasoning model on Groq",
        "is_latest": True,
        "sort_order": 1  # First in sort order to be default
    },
    {
        "name": "openai/gpt-oss-20b",
        "display_name": "GPT-OSS 20B",
        "description": "OpenAI open-weight 20B model on Groq",
        "is_latest": True,
        "sort_order": 13
    },
]

print("\nAdding Groq models:")
print("-" * 50)

added = 0
skipped = 0

for model in new_models:
    # Check if model already exists
    cursor.execute(
        "SELECT id FROM ai_model WHERE name = ? AND provider_id = ?",
        (model['name'], groq_id)
    )
    if cursor.fetchone():
        print(f"  [skip] {model['name']} already exists")
        skipped += 1
        continue

    # Add the model
    cursor.execute("""
        INSERT INTO ai_model (name, display_name, description, provider_id, is_latest, is_active, sort_order)
        VALUES (?, ?, ?, ?, ?, 1, ?)
    """, (model['name'], model['display_name'], model['description'], groq_id, model['is_latest'], model['sort_order']))
    print(f"  [added] {model['name']}")
    added += 1

# Set openai/gpt-oss-120b as default for Groq
print("\n" + "-" * 50)
print("Setting default model for Groq...")

# Get the model ID for openai/gpt-oss-120b
cursor.execute(
    "SELECT id FROM ai_model WHERE name = ? AND provider_id = ?",
    ('openai/gpt-oss-120b', groq_id)
)
row = cursor.fetchone()

if row:
    default_model_id = row[0]

    # Update api_settings to set default provider and model
    cursor.execute("SELECT id FROM api_settings LIMIT 1")
    settings_row = cursor.fetchone()

    if settings_row:
        cursor.execute("""
            UPDATE api_settings
            SET default_provider_id = ?, default_model_id = ?
            WHERE id = ?
        """, (groq_id, default_model_id, settings_row[0]))
        print(f"  [set] Default provider: Groq (ID: {groq_id})")
        print(f"  [set] Default model: openai/gpt-oss-120b (ID: {default_model_id})")
    else:
        print("  [warn] No api_settings found")
else:
    print("  [warn] openai/gpt-oss-120b model not found")

conn.commit()
conn.close()

print("\n" + "=" * 50)
print(f"Done! Added: {added}, Skipped: {skipped}")
print("Default: Groq / openai/gpt-oss-120b")
print("\nRestart the app to see the changes.")
