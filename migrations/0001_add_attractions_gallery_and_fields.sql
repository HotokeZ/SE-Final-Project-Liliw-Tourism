-- Migration: Add gallery_urls and useful columns to `attractions`
-- Run this in Supabase SQL editor or via psql connected to your project

ALTER TABLE public.attractions
-- JSONB array to store gallery image URLs
ADD COLUMN IF NOT EXISTS gallery_urls JSONB DEFAULT '[]'::jsonb,
-- Coordinates
ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION,
-- Best time fields (we store the packed string and optional start/end values)
ADD COLUMN IF NOT EXISTS best_time VARCHAR,
ADD COLUMN IF NOT EXISTS best_date_start VARCHAR,
ADD COLUMN IF NOT EXISTS best_date_end VARCHAR,
-- Duration split fields (optional; UI also writes packed `duration` string to existing column)
ADD COLUMN IF NOT EXISTS duration_min_value NUMERIC,
ADD COLUMN IF NOT EXISTS duration_min_unit VARCHAR,
ADD COLUMN IF NOT EXISTS duration_max_value NUMERIC,
ADD COLUMN IF NOT EXISTS duration_max_unit VARCHAR;

-- Optional: ensure gallery_urls is non-null
UPDATE public.attractions SET gallery_urls = '[]'::jsonb WHERE gallery_urls IS NULL;

-- You may also want to add indexes for geolocation queries (optional)
-- CREATE INDEX IF NOT EXISTS idx_attractions_location ON public.attractions USING GIST (ST_MakePoint(longitude, latitude));

-- Migration complete
