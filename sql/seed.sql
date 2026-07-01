-- seed.sql
-- Initial company list. Rerun-safe via ON CONFLICT.
-- Update this whenever companies.json changes, then run in Supabase SQL editor.
--
-- ats_slug format reminder:
--   greenhouse: 'anthropic'
--   ashby:      'mistral'
--   lever:      'spotify'
--   workday:    'wd5/garmin/External' (host subdomain / tenant / site)
--
-- Slugs below were cross-checked against a bulk ATS company-slug dataset
-- (July 2026) — see data/*.csv and scripts/expand_companies.py. Several of
-- the original "verify slug" guesses were wrong; those are marked "corrected"
-- below rather than "verify slug".

insert into companies (name, ats_type, ats_slug, tier, active, source, notes) values
  -- ─── Dream (AI labs) ───
  ('Anthropic',       'greenhouse', 'anthropic',    'dream',   true,  'manual', 'AI safety lab'),
  ('OpenAI',          'ashby',      'openai',       'dream',   true,  'manual', 'corrected: was greenhouse, actually ashby'),
  ('Google DeepMind', 'workday',    'wd5/google/External',  'dream', false, 'manual', 'Workday; not in ATS dataset — Google uses a custom careers site, not myworkdayjobs.com. Verify manually.'),
  ('NVIDIA',          'workday',    'wd5/nvidia/nvidiaexternalcareersite', 'dream', true,  'manual', 'Workday; slug verified against ATS dataset'),
  ('Mistral',         'ashby',      'mistral',      'dream',   true,  'manual', 'AI lab, Paris'),
  ('Cohere',          'ashby',      'cohere',       'dream',   true,  'manual', 'corrected: was greenhouse, actually ashby'),

  -- ─── Strong (high-impact AI + AI-adjacent) ───
  ('Stripe',          'greenhouse', 'stripe',       'strong',  true,  'manual', null),
  ('Notion',          'ashby',      'notion',       'strong',  true,  'manual', 'corrected: was greenhouse, actually ashby'),
  ('Figma',           'greenhouse', 'figma',        'strong',  true,  'manual', 'slug verified'),
  ('Vercel',          'greenhouse', 'vercel',       'strong',  true,  'manual', 'slug verified'),
  ('Linear',          'ashby',      'linear',       'strong',  true,  'manual', null),
  ('Ramp',            'ashby',      'ramp',         'strong',  true,  'manual', null),
  ('Perplexity',      'ashby',      'perplexity',   'strong',  true,  'manual', 'slug verified'),
  ('Scale AI',        'greenhouse', 'scaleai',      'strong',  true,  'manual', 'slug verified'),
  ('Databricks',      'greenhouse', 'databricks',   'strong',  true,  'manual', 'slug verified'),
  ('Hugging Face',    'greenhouse', 'huggingface',  'strong',  false, 'manual', 'not on greenhouse/ashby/lever/workday — only found on Workable in the ATS dataset, which this pipeline does not support yet. Left inactive.'),
  ('Character.AI',    'ashby',      'character',    'strong',  true,  'manual', 'slug verified'),
  ('Cursor',           'ashby',      'cursor',       'strong',  true,  'manual', 'corrected: slug is cursor, not anysphere'),
  ('Glean',           'greenhouse', 'gleanwork',    'strong',  true,  'manual', 'corrected: slug is gleanwork, not glean'),
  ('Harvey',           'ashby',      'harvey',       'strong',  true,  'manual', 'slug verified'),
  ('ElevenLabs',      'ashby',      'elevenlabs',   'strong',  true,  'manual', 'corrected: was greenhouse, actually ashby'),
  ('Runway',           'ashby',      'runway-ml',    'strong',  true,  'manual', 'corrected: slug is runway-ml — "runway" alone is a different company (Runway Financial)'),
  ('Replicate',       'ashby',      'replicate',    'strong',  true,  'manual', null),
  ('Together AI',     'greenhouse', 'togetherai',   'strong',  true,  'manual', 'corrected: was ashby, actually greenhouse'),
  ('Modal',            'ashby',      'modal',        'strong',  true,  'manual', null),
  ('LangChain',        'ashby',      'langchain',    'strong',  true,  'manual', 'slug verified'),
  ('Sierra',            'ashby',      'sierra',       'strong',  true,  'manual', 'AI agents — slug verified'),

  -- ─── Explore (broader tech + lifestyle/health) ───
  ('Airtable',        'greenhouse', 'airtable',     'explore', true,  'manual', 'slug verified'),
  ('Datadog',           'greenhouse', 'datadog',      'explore', true,  'manual', 'slug verified'),
  ('Asana',             'greenhouse', 'asana',        'explore', true,  'manual', 'slug verified'),
  ('Discord',           'greenhouse', 'discord',      'explore', true,  'manual', 'slug verified'),
  ('Strava',           'ashby',      'strava',       'explore', true,  'manual', 'corrected: was greenhouse, actually ashby — fits active/dive interest'),
  ('Mercury',           'greenhouse', 'mercury',      'explore', true,  'manual', 'slug verified'),
  ('Mercor',             'ashby',      'mercor',       'explore', true,  'manual', 'slug verified'),
  ('Garmin',           'workday',    'wd5/garmin/External', 'explore', false, 'manual', 'Workday; not in ATS dataset — Garmin actually runs on iCIMS (careers-garmin.icims.com), not Workday. This pipeline does not support iCIMS yet. Left inactive.')

on conflict (ats_type, ats_slug) do update set
  name   = excluded.name,
  tier   = excluded.tier,
  active = excluded.active,
  source = excluded.source,
  notes  = excluded.notes;
