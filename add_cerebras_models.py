#!/usr/bin/env python3
"""
Add Cerebras models to existing database.
Run: python add_cerebras_models.py
"""
import sqlite3
import os

# Find database
DB_PATHS = [
    'instance/sketchmaker.db',
    'sketchmaker.db',
    '/var/python/sketchmaker/sketchmaker/instance/sketchmaker.db'
]

db_path = None
for path in DB_PATHS:
    if os.path.exists(path):
        db_path = path
        break

if not db_path:
    print("Error: Database not found")
    exit(1)

print(f"Database: {db_path}")
print("=" * 50)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get or create Cerebras provider
c.execute("SELECT id FROM api_provider WHERE name = 'Cerebras'")
result = c.fetchone()

if not result:
    print("Cerebras provider not found, creating it...")
    c.execute("""
        INSERT INTO api_provider (name, is_active)
        VALUES ('Cerebras', 1)
    """)
    conn.commit()
    cerebras_id = c.lastrowid
    print(f"Created Cerebras provider with ID: {cerebras_id}\n")
else:
    cerebras_id = result[0]
    print(f"Cerebras provider ID: {cerebras_id}\n")

# Cerebras models to add - Latest as of December 2025
cerebras_models = [
    {
        "name": "zai-glm-4.6",
        "display_name": "ZAI GLM 4.6",
        "description": "Latest GLM model on Cerebras",
        "is_latest": True,
        "sort_order": 1
    },
    {
        "name": "llama-3.3-70b",
        "display_name": "Llama 3.3 70B",
        "description": "Multilingual Llama with ultra-fast inference",
        "is_latest": True,
        "sort_order": 2
    },
    {
        "name": "qwen-3-235b-a22b-instruct-2507",
        "display_name": "Qwen 3 235B A22B Instruct",
        "description": "MoE with 22B active params, 262K context",
        "is_latest": True,
        "sort_order": 3
    },
    {
        "name": "qwen-3-32b",
        "display_name": "Qwen 3 32B",
        "description": "Fast reasoning model, 60x faster than competitors",
        "is_latest": True,
        "sort_order": 4
    },
    {
        "name": "gpt-oss-120b",
        "display_name": "GPT-OSS 120B",
        "description": "OpenAI's open-weight 120B reasoning model",
        "is_latest": True,
        "sort_order": 5
    }
]

print("Adding Cerebras models:")
print("-" * 50)

added = 0
skipped = 0

for model in cerebras_models:
    # Check if model exists
    c.execute(
        "SELECT id FROM ai_model WHERE name = ? AND provider_id = ?",
        (model['name'], cerebras_id)
    )
    if c.fetchone():
        print(f"  [skipped] {model['name']} (already exists)")
        skipped += 1
        continue

    # Insert model
    c.execute("""
        INSERT INTO ai_model (name, display_name, description, provider_id, is_latest, sort_order, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    """, (
        model['name'],
        model['display_name'],
        model['description'],
        cerebras_id,
        1 if model.get('is_latest') else 0,
        model.get('sort_order', 0)
    ))
    print(f"  [added] {model['name']}")
    added += 1

conn.commit()
conn.close()

print("\n" + "=" * 50)
print(f"Done! Added: {added}, Skipped: {skipped}")
print("\nRestart the app to see the changes.")
