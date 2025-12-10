#!/usr/bin/env python3
"""
Test script to verify LiteLLM + Groq integration works correctly.
Run: uv run test_litellm.py
"""
import os
import sys

# Check if litellm is installed
try:
    from litellm import completion
    print("✓ LiteLLM imported successfully")
except ImportError:
    print("✗ LiteLLM not installed. Run: uv sync")
    sys.exit(1)

# Get Groq API key from environment or prompt
groq_key = os.environ.get('GROQ_API_KEY')
if not groq_key:
    groq_key = input("Enter your Groq API key: ").strip()

if not groq_key:
    print("✗ No Groq API key provided")
    sys.exit(1)

# Set environment variable
os.environ['GROQ_API_KEY'] = groq_key

# Test models to try
test_models = [
    "groq/llama-3.1-8b-instant",  # Standard Groq model (should work)
    "groq/qwen/qwen3-32b",        # Qwen model on Groq
    "groq/openai/gpt-oss-120b",   # GPT-OSS model on Groq
]

print("\n" + "="*60)
print("Testing LiteLLM + Groq Integration")
print("="*60)

for model in test_models:
    print(f"\n→ Testing model: {model}")
    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": "Say 'Hello, LiteLLM works!' in exactly 5 words."}],
            max_tokens=50,
            api_key=groq_key
        )
        result = response.choices[0].message.content.strip()
        print(f"  ✓ Response: {result}")
    except Exception as e:
        print(f"  ✗ Error: {str(e)}")

print("\n" + "="*60)
print("Test complete")
print("="*60)
