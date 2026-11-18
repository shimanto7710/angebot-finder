-- Existing accounts keep an unknown name until their profile is updated.
ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE users ADD CONSTRAINT users_name_length
    CHECK (name IS NULL OR length(trim(name)) BETWEEN 1 AND 100);
