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

# Get Cerebras provider ID
c.execute("SELECT id FROM api_provider WHERE name = 'Cerebras'")
result = c.fetchone()

if not result:
    print("Error: Cerebras provider not found in database")
    print("Run migrations first: python migrations/migrate_all.py")
    exit(1)

cerebras_id = result[0]
print(f"Cerebras provider ID: {cerebras_id}\n")

# Cerebras models to add
cerebras_models = [
    {
        "name": "qwen3-coder-480b",
        "display_name": "Qwen3 Coder 480B",
        "description": "Top coding model at 2,000 tokens/sec",
        "is_latest": True,
        "sort_order": 1
    },
    {
        "name": "qwen3-235b-a22b",
        "display_name": "Qwen3 235B A22B",
        "description": "MoE with 22B active params, 262K context",
        "is_latest": True,
        "sort_order": 2
    },
    {
        "name": "qwen3-32b",
        "display_name": "Qwen3 32B",
        "description": "Real-time reasoning at 60x faster than competitors",
        "is_latest": True,
        "sort_order": 3
    },
    {
        "name": "llama-4-maverick",
        "display_name": "Llama 4 Maverick",
        "description": "400B Llama 4 at 2,500+ tokens/sec world record",
        "is_latest": True,
        "sort_order": 4
    },
    {
        "name": "llama-3.3-70b",
        "display_name": "Llama 3.3 70B",
        "description": "Multilingual Llama with fast inference",
        "sort_order": 5
    },
    {
        "name": "deepseek-r1-distill-llama-70b",
        "display_name": "DeepSeek R1 Distill 70B",
        "description": "DeepSeek reasoning model on Cerebras",
        "sort_order": 6
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
