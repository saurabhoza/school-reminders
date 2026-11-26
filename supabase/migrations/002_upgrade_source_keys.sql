-- Upgrade databases created from the first Gmail-only version of migration 001.
-- Safe to run against the current schema as well.
ALTER TABLE source_emails ADD COLUMN IF NOT EXISTS source_key TEXT;
ALTER TABLE source_emails ADD COLUMN IF NOT EXISTS source_type TEXT;
ALTER TABLE source_emails ADD COLUMN IF NOT EXISTS source_reference TEXT NOT NULL DEFAULT '';
ALTER TABLE source_emails ADD COLUMN IF NOT EXISTS source_text TEXT NOT NULL DEFAULT '';

UPDATE source_emails
SET source_key = gmail_message_id,
    source_type = COALESCE(source_type, 'gmail'),
    source_reference = CASE WHEN source_reference = '' THEN gmail_message_id ELSE source_reference END
WHERE source_key IS NULL;

ALTER TABLE reminders ADD COLUMN IF NOT EXISTS source_key TEXT;
UPDATE reminders
SET source_key = source_emails.source_key
FROM source_emails
WHERE reminders.source_key IS NULL
  AND reminders.gmail_message_id = source_emails.gmail_message_id;

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    FOR constraint_name IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'reminders'::regclass
          AND (contype = 'f' OR contype = 'u')
          AND pg_get_constraintdef(oid) LIKE '%gmail_message_id%'
    LOOP
        EXECUTE format('ALTER TABLE reminders DROP CONSTRAINT %I', constraint_name);
    END LOOP;
    FOR constraint_name IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'source_emails'::regclass AND contype = 'p'
    LOOP
        EXECUTE format('ALTER TABLE source_emails DROP CONSTRAINT %I', constraint_name);
    END LOOP;
END $$;

ALTER TABLE source_emails ALTER COLUMN source_key SET NOT NULL;
ALTER TABLE source_emails ALTER COLUMN source_type SET DEFAULT 'gmail';
ALTER TABLE source_emails ALTER COLUMN source_type SET NOT NULL;
ALTER TABLE source_emails ALTER COLUMN gmail_message_id DROP NOT NULL;
ALTER TABLE source_emails ALTER COLUMN received_at DROP NOT NULL;

ALTER TABLE source_emails ADD CONSTRAINT source_emails_pkey PRIMARY KEY (source_key);
CREATE UNIQUE INDEX IF NOT EXISTS source_emails_gmail_message_id_key
    ON source_emails(gmail_message_id) WHERE gmail_message_id IS NOT NULL;

ALTER TABLE reminders ALTER COLUMN source_key SET NOT NULL;

ALTER TABLE reminders DROP CONSTRAINT IF EXISTS reminders_source_key_fkey;
ALTER TABLE reminders DROP CONSTRAINT IF EXISTS reminders_source_key_notice_index_key;
ALTER TABLE reminders
    ADD CONSTRAINT reminders_source_key_fkey
    FOREIGN KEY (source_key) REFERENCES source_emails(source_key) ON DELETE CASCADE;
ALTER TABLE reminders
    ADD CONSTRAINT reminders_source_key_notice_index_key UNIQUE (source_key, notice_index);
