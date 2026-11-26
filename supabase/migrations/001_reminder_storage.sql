CREATE TABLE IF NOT EXISTS source_emails (
    source_key TEXT PRIMARY KEY,
    source_type TEXT CHECK (source_type IN ('gmail', 'pasted_email', 'sway')),
    gmail_message_id TEXT UNIQUE,
    source_reference TEXT DEFAULT '',
    source_text TEXT DEFAULT '',
    thread_id TEXT DEFAULT '',
    sender TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    received_at TIMESTAMPTZ,
    rfc_message_id TEXT DEFAULT '',
    processed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reminders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key TEXT REFERENCES source_emails(source_key) ON DELETE CASCADE,
    notice_index INTEGER CHECK (notice_index >= 0),
    title TEXT,
    event_date_text TEXT,
    event_date DATE,
    years TEXT[] DEFAULT '{}',
    classes TEXT[] DEFAULT '{}',
    date_evidence JSONB,
    evidence JSONB,
    audience_evidence JSONB,
    review_required BOOLEAN DEFAULT false,
    status TEXT DEFAULT 'pending'
        CHECK (status IN ('pending', 'scheduled', 'completed', 'cancelled')),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source_key, notice_index)
);

CREATE INDEX IF NOT EXISTS reminders_event_date_idx ON reminders(event_date);
CREATE INDEX IF NOT EXISTS reminders_years_idx ON reminders USING GIN(years);
CREATE INDEX IF NOT EXISTS reminders_classes_idx ON reminders USING GIN(classes);

CREATE TABLE IF NOT EXISTS reminder_deliveries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reminder_id BIGINT REFERENCES reminders(id) ON DELETE CASCADE,
    scheduled_for TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    delivery_status TEXT DEFAULT 'scheduled'
        CHECK (delivery_status IN ('scheduled', 'sent', 'failed', 'cancelled')),
    UNIQUE (reminder_id, scheduled_for)
);
