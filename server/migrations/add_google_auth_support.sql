-- Add auth_settings table
CREATE TABLE IF NOT EXISTS auth_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regular_auth_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    google_auth_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    google_client_id VARCHAR(255),
    google_client_secret VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create temporary table with new schema
CREATE TABLE user_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(128) NOT NULL,
    created_at DATETIME,
    role VARCHAR(20),
    is_active BOOLEAN,
    is_approved BOOLEAN,
    selected_provider_id INTEGER,
    selected_model_id INTEGER,
    openai_api_key VARCHAR(255),
    anthropic_api_key VARCHAR(255),
    gemini_api_key VARCHAR(255),
    groq_api_key VARCHAR(255),
    fal_key VARCHAR(255),
    google_id VARCHAR(255) UNIQUE,
    FOREIGN KEY(selected_provider_id) REFERENCES api_provider (id),
    FOREIGN KEY(selected_model_id) REFERENCES ai_model (id)
);

-- Copy data from old table to new table
INSERT INTO user_new (
    id, username, email, password_hash, created_at, role, is_active, is_approved,
    selected_provider_id, selected_model_id, openai_api_key, anthropic_api_key,
    gemini_api_key, groq_api_key, fal_key
)
SELECT 
    id, username, email, password_hash, created_at, role, is_active, is_approved,
    selected_provider_id, selected_model_id, openai_api_key, anthropic_api_key,
    gemini_api_key, groq_api_key, fal_key
FROM user;

-- Drop old table
DROP TABLE user;

-- Rename new table to user
ALTER TABLE user_new RENAME TO user;

-- Insert default auth settings if not exists
INSERT INTO auth_settings (regular_auth_enabled, google_auth_enabled)
SELECT TRUE, FALSE
WHERE NOT EXISTS (SELECT 1 FROM auth_settings LIMIT 1);
