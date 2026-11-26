-- Keep primary keys non-null because Postgres requires this for row identity.
-- All other stored values are optional so partial or unknown data can be saved.
ALTER TABLE source_emails
    ALTER COLUMN source_type DROP NOT NULL,
    ALTER COLUMN gmail_message_id DROP NOT NULL,
    ALTER COLUMN source_reference DROP NOT NULL,
    ALTER COLUMN source_text DROP NOT NULL,
    ALTER COLUMN thread_id DROP NOT NULL,
    ALTER COLUMN sender DROP NOT NULL,
    ALTER COLUMN subject DROP NOT NULL,
    ALTER COLUMN received_at DROP NOT NULL,
    ALTER COLUMN rfc_message_id DROP NOT NULL,
    ALTER COLUMN processed_at DROP NOT NULL;

ALTER TABLE reminders
    ALTER COLUMN source_key DROP NOT NULL,
    ALTER COLUMN notice_index DROP NOT NULL,
    ALTER COLUMN title DROP NOT NULL,
    ALTER COLUMN event_date_text DROP NOT NULL,
    ALTER COLUMN event_date DROP NOT NULL,
    ALTER COLUMN years DROP NOT NULL,
    ALTER COLUMN classes DROP NOT NULL,
    ALTER COLUMN date_evidence DROP NOT NULL,
    ALTER COLUMN evidence DROP NOT NULL,
    ALTER COLUMN audience_evidence DROP NOT NULL,
    ALTER COLUMN review_required DROP NOT NULL,
    ALTER COLUMN status DROP NOT NULL,
    ALTER COLUMN created_at DROP NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'reminders'
          AND column_name = 'gmail_message_id'
    ) THEN
        ALTER TABLE public.reminders ALTER COLUMN gmail_message_id DROP NOT NULL;
    END IF;
END $$;

ALTER TABLE reminder_deliveries
    ALTER COLUMN reminder_id DROP NOT NULL,
    ALTER COLUMN scheduled_for DROP NOT NULL,
    ALTER COLUMN sent_at DROP NOT NULL,
    ALTER COLUMN delivery_status DROP NOT NULL;
