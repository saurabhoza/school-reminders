CREATE TABLE IF NOT EXISTS source_emails (
    gmail_message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    received_at TIMESTAMPTZ NOT NULL,
    rfc_message_id TEXT NOT NULL DEFAULT '',
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reminders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gmail_message_id TEXT NOT NULL REFERENCES source_emails(gmail_message_id) ON DELETE CASCADE,
    notice_index INTEGER NOT NULL CHECK (notice_index >= 0),
    title TEXT NOT NULL,
    event_date_text TEXT NOT NULL,
    event_date DATE,
    years TEXT[] NOT NULL DEFAULT '{}',
    classes TEXT[] NOT NULL DEFAULT '{}',
    date_evidence JSONB NOT NULL,
    evidence JSONB NOT NULL,
    audience_evidence JSONB NOT NULL,
    review_required BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'scheduled', 'completed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (gmail_message_id, notice_index)
);

CREATE INDEX IF NOT EXISTS reminders_event_date_idx ON reminders(event_date);
CREATE INDEX IF NOT EXISTS reminders_years_idx ON reminders USING GIN(years);
CREATE INDEX IF NOT EXISTS reminders_classes_idx ON reminders USING GIN(classes);

CREATE TABLE IF NOT EXISTS reminder_deliveries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reminder_id BIGINT NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
    scheduled_for TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    delivery_status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (delivery_status IN ('scheduled', 'sent', 'failed', 'cancelled')),
    UNIQUE (reminder_id, scheduled_for)
);
