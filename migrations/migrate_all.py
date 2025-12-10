#!/usr/bin/env python3
"""
Consolidated Migration Script for SketchMaker AI
Run this script to apply all database migrations directly using SQLite.

Tracks migration status using alembic_version table for compatibility with Flask-Migrate.

Usage:
    cd migrations
    uv run migrate_all.py
    cd ..
"""

import sqlite3
import os
import sys
from datetime import datetime

# Change to parent directory where database is located
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(parent_dir)

# Database path - check multiple locations
DB_PATHS = [
    os.path.join(parent_dir, 'instance', 'sketchmaker.db'),
    os.path.join(parent_dir, 'sketchmaker.db'),
]

DB_PATH = None
for path in DB_PATHS:
    if os.path.exists(path):
        DB_PATH = path
        break

if not DB_PATH:
    print("Error: Database not found.")
    print("Checked locations:")
    for path in DB_PATHS:
        print(f"  - {path}")
    print("\nMake sure the database exists before running migrations.")
    sys.exit(1)


# Migration registry - maps revision ID to migration info
MIGRATIONS = {
    'add_subscription_system': {
        'description': 'Subscription system tables',
        'depends_on': None,
    },
    'add_centralized_api_management': {
        'description': 'Centralized API management',
        'depends_on': 'add_subscription_system',
    },
    'add_google_auth_support': {
        'description': 'Google OAuth support',
        'depends_on': 'add_centralized_api_management',
    },
    'add_feature_usage_tracking': {
        'description': 'Feature usage tracking',
        'depends_on': 'add_google_auth_support',
    },
    'add_credit_security_constraints': {
        'description': 'Credit security constraints',
        'depends_on': 'add_feature_usage_tracking',
    },
    'add_new_litellm_providers': {
        'description': 'LiteLLM providers (xAI, Cerebras, OpenRouter)',
        'depends_on': 'add_credit_security_constraints',
    },
}


def get_table_columns(cursor, table_name):
    """Get set of column names for a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def table_exists(cursor, table_name):
    """Check if a table exists"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def get_current_revision(cursor):
    """Get current alembic revision"""
    if not table_exists(cursor, 'alembic_version'):
        return None
    cursor.execute("SELECT version_num FROM alembic_version")
    row = cursor.fetchone()
    return row[0] if row else None


def set_revision(cursor, revision):
    """Set alembic revision"""
    if not table_exists(cursor, 'alembic_version'):
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        cursor.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (revision,))
    else:
        cursor.execute("DELETE FROM alembic_version")
        cursor.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (revision,))


def get_applied_migrations(cursor):
    """Determine which migrations have been applied based on schema state"""
    applied = set()

    # Check for subscription system
    if table_exists(cursor, 'subscription_plan') and table_exists(cursor, 'user_subscription'):
        applied.add('add_subscription_system')

    # Check for centralized API management
    if table_exists(cursor, 'api_settings'):
        applied.add('add_centralized_api_management')

    # Check for Google auth
    if table_exists(cursor, 'user'):
        user_cols = get_table_columns(cursor, 'user')
        if 'google_id' in user_cols:
            applied.add('add_google_auth_support')

    # Check for feature usage
    if table_exists(cursor, 'feature_usage'):
        applied.add('add_feature_usage_tracking')

    # Check for credit security (credit_cost_config table)
    if table_exists(cursor, 'credit_cost_config'):
        applied.add('add_credit_security_constraints')

    # Check for LiteLLM providers
    if table_exists(cursor, 'api_settings'):
        cols = get_table_columns(cursor, 'api_settings')
        if 'xai_api_key' in cols and 'cerebras_api_key' in cols:
            applied.add('add_new_litellm_providers')

    return applied


def run_migrations():
    """Run all database migrations directly using SQLite"""
    print("=" * 70)
    print("SketchMaker AI - Consolidated Database Migration")
    print("=" * 70)
    print(f"\nDatabase: {DB_PATH}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Get current state
        current_revision = get_current_revision(cursor)
        applied_migrations = get_applied_migrations(cursor)

        print(f"\nCurrent alembic revision: {current_revision or '(none)'}")

        # Show migration status
        print("\n" + "-" * 70)
        print("MIGRATION STATUS")
        print("-" * 70)
        print(f"{'Revision':<35} {'Description':<25} {'Status':<10}")
        print("-" * 70)

        for rev_id, info in MIGRATIONS.items():
            if rev_id in applied_migrations:
                status = "DONE"
                status_color = "✓"
            else:
                status = "PENDING"
                status_color = "○"
            print(f"{status_color} {rev_id:<33} {info['description']:<25} {status:<10}")

        print("-" * 70)

        # Determine what needs to be applied
        pending = [rev for rev in MIGRATIONS.keys() if rev not in applied_migrations]

        if not pending:
            print("\n✓ All migrations already applied. Database is up to date.")
            conn.close()
            return

        print(f"\nApplying {len(pending)} pending migration(s)...")
        migrations_applied = []

        # ============================================================
        # Migration: add_subscription_system
        # ============================================================
        if 'add_subscription_system' in pending:
            print("\n[1/6] Applying: add_subscription_system")

            if not table_exists(cursor, 'subscription_plan'):
                cursor.execute("""
                    CREATE TABLE subscription_plan (
                        id INTEGER PRIMARY KEY,
                        name VARCHAR(50) NOT NULL UNIQUE,
                        display_name VARCHAR(100),
                        description TEXT,
                        monthly_credits INTEGER DEFAULT 0,
                        price_monthly FLOAT DEFAULT 0,
                        price_yearly FLOAT DEFAULT 0,
                        features TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                """)
                print("       + Created subscription_plan table")

            if not table_exists(cursor, 'user_subscription'):
                cursor.execute("""
                    CREATE TABLE user_subscription (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        plan_id INTEGER NOT NULL,
                        credits_remaining INTEGER DEFAULT 0,
                        credits_used_this_month INTEGER DEFAULT 0,
                        billing_cycle_start DATETIME,
                        billing_cycle_end DATETIME,
                        is_active BOOLEAN DEFAULT 1,
                        created_at DATETIME,
                        updated_at DATETIME,
                        FOREIGN KEY (user_id) REFERENCES user(id),
                        FOREIGN KEY (plan_id) REFERENCES subscription_plan(id)
                    )
                """)
                print("       + Created user_subscription table")

            if not table_exists(cursor, 'credit_transaction'):
                cursor.execute("""
                    CREATE TABLE credit_transaction (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        amount INTEGER NOT NULL,
                        transaction_type VARCHAR(50) NOT NULL,
                        description TEXT,
                        metadata TEXT,
                        created_at DATETIME,
                        FOREIGN KEY (user_id) REFERENCES user(id)
                    )
                """)
                print("       + Created credit_transaction table")

            migrations_applied.append('add_subscription_system')

        # ============================================================
        # Migration: add_centralized_api_management
        # ============================================================
        if 'add_centralized_api_management' in pending:
            print("\n[2/6] Applying: add_centralized_api_management")

            if not table_exists(cursor, 'api_settings'):
                cursor.execute("""
                    CREATE TABLE api_settings (
                        id INTEGER PRIMARY KEY,
                        openai_api_key TEXT,
                        anthropic_api_key TEXT,
                        gemini_api_key TEXT,
                        groq_api_key TEXT,
                        fal_key TEXT,
                        default_provider_id INTEGER,
                        default_model_id INTEGER,
                        encryption_key TEXT,
                        created_at DATETIME,
                        updated_at DATETIME,
                        updated_by_id INTEGER,
                        FOREIGN KEY (default_model_id) REFERENCES ai_model(id),
                        FOREIGN KEY (default_provider_id) REFERENCES api_provider(id),
                        FOREIGN KEY (updated_by_id) REFERENCES user(id)
                    )
                """)
                print("       + Created api_settings table")

            migrations_applied.append('add_centralized_api_management')

        # ============================================================
        # Migration: add_google_auth_support
        # ============================================================
        if 'add_google_auth_support' in pending:
            print("\n[3/6] Applying: add_google_auth_support")

            if table_exists(cursor, 'user'):
                user_columns = get_table_columns(cursor, 'user')

                if 'google_id' not in user_columns:
                    cursor.execute("ALTER TABLE user ADD COLUMN google_id VARCHAR(100)")
                    print("       + Added user.google_id column")

                if 'auth_provider' not in user_columns:
                    cursor.execute("ALTER TABLE user ADD COLUMN auth_provider VARCHAR(20) DEFAULT 'local'")
                    print("       + Added user.auth_provider column")

                if 'profile_picture' not in user_columns:
                    cursor.execute("ALTER TABLE user ADD COLUMN profile_picture VARCHAR(500)")
                    print("       + Added user.profile_picture column")

            if not table_exists(cursor, 'auth_settings'):
                cursor.execute("""
                    CREATE TABLE auth_settings (
                        id INTEGER PRIMARY KEY,
                        google_auth_enabled BOOLEAN DEFAULT 0,
                        google_client_id VARCHAR(500),
                        google_client_secret VARCHAR(500),
                        require_approval BOOLEAN DEFAULT 1,
                        updated_at DATETIME,
                        updated_by_id INTEGER,
                        FOREIGN KEY (updated_by_id) REFERENCES user(id)
                    )
                """)
                print("       + Created auth_settings table")

            migrations_applied.append('add_google_auth_support')

        # ============================================================
        # Migration: add_feature_usage_tracking
        # ============================================================
        if 'add_feature_usage_tracking' in pending:
            print("\n[4/6] Applying: add_feature_usage_tracking")

            if not table_exists(cursor, 'feature_usage'):
                cursor.execute("""
                    CREATE TABLE feature_usage (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        feature_name VARCHAR(100) NOT NULL,
                        credits_used INTEGER DEFAULT 1,
                        metadata TEXT,
                        created_at DATETIME,
                        FOREIGN KEY (user_id) REFERENCES user(id)
                    )
                """)
                print("       + Created feature_usage table")

            migrations_applied.append('add_feature_usage_tracking')

        # ============================================================
        # Migration: add_credit_security_constraints
        # ============================================================
        if 'add_credit_security_constraints' in pending:
            print("\n[5/6] Applying: add_credit_security_constraints")

            if not table_exists(cursor, 'credit_cost_config'):
                cursor.execute("""
                    CREATE TABLE credit_cost_config (
                        id INTEGER PRIMARY KEY,
                        feature_name VARCHAR(100) NOT NULL UNIQUE,
                        credit_cost FLOAT DEFAULT 1.0,
                        description TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        updated_at DATETIME,
                        updated_by_id INTEGER,
                        FOREIGN KEY (updated_by_id) REFERENCES user(id)
                    )
                """)
                print("       + Created credit_cost_config table")

            migrations_applied.append('add_credit_security_constraints')

        # ============================================================
        # Migration: add_new_litellm_providers
        # ============================================================
        if 'add_new_litellm_providers' in pending:
            print("\n[6/6] Applying: add_new_litellm_providers")

            if table_exists(cursor, 'api_settings'):
                columns = get_table_columns(cursor, 'api_settings')

                if 'xai_api_key' not in columns:
                    cursor.execute("ALTER TABLE api_settings ADD COLUMN xai_api_key TEXT")
                    print("       + Added api_settings.xai_api_key column")

                if 'cerebras_api_key' not in columns:
                    cursor.execute("ALTER TABLE api_settings ADD COLUMN cerebras_api_key TEXT")
                    print("       + Added api_settings.cerebras_api_key column")

                if 'openrouter_api_key' not in columns:
                    cursor.execute("ALTER TABLE api_settings ADD COLUMN openrouter_api_key TEXT")
                    print("       + Added api_settings.openrouter_api_key column")

            migrations_applied.append('add_new_litellm_providers')

        # Update alembic version to latest
        if migrations_applied:
            latest_revision = migrations_applied[-1]
            set_revision(cursor, latest_revision)
            print(f"\n       Updated alembic_version to: {latest_revision}")

        conn.commit()

        # ============================================================
        # Final Summary
        # ============================================================
        print("\n" + "=" * 70)
        print("MIGRATION COMPLETE")
        print("=" * 70)
        print(f"Applied {len(migrations_applied)} migration(s):")
        for m in migrations_applied:
            print(f"  ✓ {m}")

        print("\n" + "-" * 70)
        print("FINAL STATUS")
        print("-" * 70)

        # Re-check status
        applied_migrations = get_applied_migrations(cursor)
        for rev_id, info in MIGRATIONS.items():
            status = "✓ DONE" if rev_id in applied_migrations else "○ PENDING"
            print(f"  {rev_id:<35} {status}")

        print("-" * 70)
        print("\nSupported LiteLLM providers:")
        print("  - OpenAI (GPT-5, O3, GPT-OSS)")
        print("  - Anthropic (Claude 4.5)")
        print("  - Google Gemini (Gemini 3)")
        print("  - Groq (Compound Beta, Llama)")
        print("  - xAI (Grok 3)")
        print("  - Cerebras (Qwen3, Llama 4)")
        print("  - OpenRouter (500+ models)")
        print("\nRun 'uv run app.py' to start the application.")

    except Exception as e:
        conn.rollback()
        print(f"\nError during migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    run_migrations()
