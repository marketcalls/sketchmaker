"""Add the language models released since the first list, for existing installs.

Data only. A new install has no providers at this point and is left alone: seed_defaults
fills it from the current list when the app starts.

What it never touches: the default and fallback model, the owner's own choice, a model the
owner added or edited by hand, and a model the owner deleted that is not in this list. A
retired model stays switched on if the owner has it selected, so nothing they rely on stops
being offered without them deciding.

The data is a frozen copy, not an import of app/seed.py, because this migration must keep
doing the same thing after that list changes again.

Revision ID: 0002_latest_models
Revises: 0001_baseline
"""

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_latest_models"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# provider: [(name, display name, description, context window, is latest)]
# Go above everything the provider has now, in this order.
NEW_MODELS = {
    'OpenAI': [
        ('gpt-6.1-sol', 'GPT-6.1 Sol', 'Frontier model for complex professional work', None, True),
        ('gpt-6.1-terra', 'GPT-6.1 Terra', 'Balanced capability and cost for everyday work', None, True),
        ('gpt-6-astra', 'GPT-6 Astra', 'Highest tier of the GPT-6 family', None, True),
        ('gpt-6-sol', 'GPT-6 Sol', 'Frontier model of the GPT-6 family', None, True),
        ('gpt-6-luna', 'GPT-6 Luna', 'Most cost-efficient of the GPT-6 family', None, True),
    ],
    'Anthropic': [
        ('claude-fable-5-1', 'Claude Fable 5.1', 'Most capable, for the hardest reasoning and long-running work', 1000000, True),
        ('claude-opus-5-5', 'Claude Opus 5.5', 'For complex agentic work, at a lower price than Opus 5', 1000000, True),
        ('claude-sonnet-5-5', 'Claude Sonnet 5.5', 'Speed and capability for everyday work', 1000000, True),
        ('claude-haiku-5-5', 'Claude Haiku 5.5', 'Fastest and lowest cost', 1000000, True),
    ],
    'Google Gemini': [
        ('gemini-4-argon', 'Gemini 4 Argon', 'Latest Gemini generation', 1048576, True),
        ('gemini-3.8-flash', 'Gemini 3.8 Flash', 'Fast general-purpose Gemini 3.8', 1048576, True),
        ('gemini-3.7-flash', 'Gemini 3.7 Flash', 'Fast general-purpose Gemini 3.7', 1048576, False),
    ],
    'xAI': [
        ('grok-4.7', 'Grok 4.7', "xAI's most capable model", 500000, True),
        ('grok-4.6', 'Grok 4.6', 'Previous flagship', 500000, False),
    ],
    'Cerebras': [
        ('qwen-3.8-27b', 'Qwen 3.8 27B', 'Fast open-weight model', 65536, True),
    ],
    'OpenRouter': [
        ('openai/gpt-6.1-sol', 'GPT-6.1 Sol (OpenRouter)', 'OpenAI flagship via OpenRouter', 1050000, True),
        ('anthropic/claude-opus-5.5', 'Claude Opus 5.5 (OpenRouter)', 'Anthropic Opus 5.5 via OpenRouter', 1000000, True),
        ('google/gemini-4-argon', 'Gemini 4 Argon (OpenRouter)', 'Google Gemini via OpenRouter', 1048576, True),
        ('x-ai/grok-4.7', 'Grok 4.7 (OpenRouter)', 'xAI Grok via OpenRouter', 500000, True),
    ],
    'Baseten': [
        ('zai-org/GLM-5.3', 'GLM 5.3 (Baseten)', 'Z.ai GLM 5.3', None, True),
    ],
}

# Go below everything the provider has now: previews, not a new generation.
APPENDED_MODELS = {
    'Groq': [
        ('qwen/qwen3.8-27b', 'Qwen 3.8 27B (Groq preview)', 'Preview: may be discontinued at short notice', 131072, False),
        ('minimaxai/minimax-m2.7', 'MiniMax M2.7 (Groq preview)', 'Preview: may be discontinued at short notice', 196608, False),
        ('meta-models/muse-spark-open', 'Muse Spark Open (Groq preview)', 'Preview: may be discontinued at short notice', 131072, False),
    ],
}

# Still offered, but no longer the newest.
NO_LONGER_LATEST = {
    'OpenAI': ['gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna'],
    'Anthropic': ['claude-fable-5', 'claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5-20251001'],
    'Google Gemini': ['gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.5-flash-lite'],
    'xAI': ['grok-4.5'],
    'OpenRouter': ['openai/gpt-5.6-sol', 'anthropic/claude-opus-5', 'google/gemini-3.6-flash', 'x-ai/grok-4.5'],
    'Baseten': ['zai-org/GLM-5.2', 'zai-org/GLM-5.2-Fast'],
}

# No longer on the provider's public model list.
RETIRED = [
    ('Cerebras', 'gemma-4-31b'),
    ('Cerebras', 'zai-glm-4.7'),
]

api_provider = sa.table("api_provider", sa.column("id", sa.Integer), sa.column("name", sa.String))
api_settings = sa.table(
    "api_settings", sa.column("default_model_id", sa.Integer), sa.column("fallback_model_id", sa.Integer),
)
user = sa.table("user", sa.column("selected_model_id", sa.Integer))
ai_model = sa.table(
    "ai_model",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("display_name", sa.String),
    sa.column("description", sa.Text),
    sa.column("provider_id", sa.Integer),
    sa.column("context_window", sa.Integer),
    sa.column("is_latest", sa.Boolean),
    sa.column("sort_order", sa.Integer),
    sa.column("is_active", sa.Boolean),
    sa.column("created_at", sa.DateTime),
)


def _insert_missing(conn, provider_id: int, rows: list, first_sort_order: int) -> None:
    existing = {r[0] for r in conn.execute(sa.select(ai_model.c.name).where(ai_model.c.provider_id == provider_id))}
    for offset, (name, display_name, description, context_window, is_latest) in enumerate(rows):
        if name in existing:
            continue  # the owner added it by hand: theirs stands
        conn.execute(ai_model.insert().values(
            name=name, display_name=display_name, description=description, provider_id=provider_id,
            context_window=context_window, is_latest=is_latest, sort_order=first_sort_order + offset,
            is_active=True, created_at=datetime.utcnow(),
        ))


def upgrade() -> None:
    conn = op.get_bind()
    providers = {name: pid for pid, name in conn.execute(sa.select(api_provider.c.id, api_provider.c.name))}
    if not providers:
        return  # a new install

    for provider, rows in NEW_MODELS.items():
        provider_id = providers.get(provider)
        if provider_id is None:
            continue
        conn.execute(ai_model.update().where(ai_model.c.provider_id == provider_id)
                     .values(sort_order=ai_model.c.sort_order + len(rows)))
        _insert_missing(conn, provider_id, rows, 1)

    for provider, rows in APPENDED_MODELS.items():
        provider_id = providers.get(provider)
        if provider_id is None:
            continue
        highest = conn.execute(sa.select(sa.func.max(ai_model.c.sort_order))
                               .where(ai_model.c.provider_id == provider_id)).scalar() or 0
        _insert_missing(conn, provider_id, rows, highest + 1)

    for provider, names in NO_LONGER_LATEST.items():
        provider_id = providers.get(provider)
        if provider_id is not None:
            conn.execute(ai_model.update()
                         .where(ai_model.c.provider_id == provider_id, ai_model.c.name.in_(names))
                         .values(is_latest=False))

    in_use = set()
    for column in (api_settings.c.default_model_id, api_settings.c.fallback_model_id, user.c.selected_model_id):
        in_use.update(r[0] for r in conn.execute(sa.select(column)) if r[0] is not None)
    for provider, name in RETIRED:
        provider_id = providers.get(provider)
        if provider_id is None:
            continue
        for (model_id,) in conn.execute(sa.select(ai_model.c.id).where(
                ai_model.c.provider_id == provider_id, ai_model.c.name == name)).fetchall():
            if model_id not in in_use:
                conn.execute(ai_model.update().where(ai_model.c.id == model_id).values(is_active=False))


def downgrade() -> None:
    """Not used: going back means restoring the backup taken before the upgrade."""
