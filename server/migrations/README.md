# Database Migrations

This directory contains SQL migration scripts for the Sketchmaker application.

## Running Migrations

### On Production Server

1. SSH into your server
2. Navigate to the application directory:
```bash
cd /var/python/sketchmaker/sketchmaker
```

3. Backup your database (recommended):
```bash
cp instance/sketchmaker.db instance/sketchmaker.db.backup
```

4. Run the migration:
```bash
sqlite3 instance/sketchmaker.db < server/migrations/add_google_auth_support.sql
```

5. Verify the changes:
```bash
sqlite3 instance/sketchmaker.db ".schema auth_settings"
sqlite3 instance/sketchmaker.db ".schema user"
```

6. Restart the application:
```bash
sudo systemctl restart sketchmaker
```

## Migration Files

- `add_google_auth_support.sql`: Adds Google OAuth support
  - Creates auth_settings table with:
    * regular_auth_enabled (default: true)
    * google_auth_enabled (default: false)
    * google_client_id and google_client_secret fields
  - Adds google_id column to user table
  - Preserves all existing user data
  - Maintains foreign key constraints
  - Inserts default auth settings

## Rollback

If you need to rollback the changes:

1. Restore from backup:
```bash
cp instance/sketchmaker.db.backup instance/sketchmaker.db
```

2. Or run these SQL commands:
```sql
-- Drop auth_settings table
DROP TABLE IF EXISTS auth_settings;

-- Recreate user table without google_id
CREATE TABLE user_old (
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
    FOREIGN KEY(selected_provider_id) REFERENCES api_provider (id),
    FOREIGN KEY(selected_model_id) REFERENCES ai_model (id)
);

-- Copy data back
INSERT INTO user_old 
SELECT id, username, email, password_hash, created_at, role, is_active, is_approved,
       selected_provider_id, selected_model_id, openai_api_key, anthropic_api_key,
       gemini_api_key, groq_api_key, fal_key
FROM user;

-- Drop new table and rename old table
DROP TABLE user;
ALTER TABLE user_old RENAME TO user;
```

3. Restart the application:
```bash
sudo systemctl restart sketchmaker
```

## After Migration

After applying the migration:
1. Login as superadmin
2. Go to /admin/manage/auth
3. Configure Google OAuth:
   - Enable/disable Google authentication
   - Add Google OAuth client ID and secret
4. Test the authentication flow
