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
-- Note: slugs marked "verify" in notes need to be confirmed against each
-- company's live careers page before enabling. Visit careers.{company}.com
-- and check the URL pattern. Workday slugs especially vary by tenant.

insert into companies (name, ats_type, ats_slug, tier, active, source, notes) values
  -- ─── Dream (AI labs) ───
  ('Anthropic',       'greenhouse', 'anthropic',    'dream',   true,  'manual', 'AI safety lab'),
  ('OpenAI',          'greenhouse', 'openai',       'dream',   true,  'manual', 'verify slug'),
  ('Google DeepMind', 'workday',    'wd5/google/External',  'dream', false, 'manual', 'Workday; verify tenant + site'),
  ('NVIDIA',          'workday',    'wd5/nvidia/NVIDIAExternalCareerSite', 'dream', false, 'manual', 'Workday; verify site name'),
  ('Mistral',         'ashby',      'mistral',      'dream',   true,  'manual', 'AI lab, Paris'),
  ('Cohere',          'greenhouse', 'cohere',       'dream',   true,  'manual', 'verify slug'),

  -- ─── Strong (high-impact AI + AI-adjacent) ───
  ('Stripe',          'greenhouse', 'stripe',       'strong',  true,  'manual', null),
  ('Notion',          'greenhouse', 'notion',       'strong',  true,  'manual', 'verify slug'),
  ('Figma',           'greenhouse', 'figma',        'strong',  true,  'manual', 'verify slug'),
  ('Vercel',          'greenhouse', 'vercel',       'strong',  true,  'manual', 'verify slug'),
  ('Linear',          'ashby',      'linear',       'strong',  true,  'manual', null),
  ('Ramp',            'ashby',      'ramp',         'strong',  true,  'manual', null),
  ('Perplexity',      'ashby',      'perplexity',   'strong',  true,  'manual', 'verify slug'),
  ('Scale AI',        'greenhouse', 'scaleai',      'strong',  true,  'manual', 'verify slug'),
  ('Databricks',      'greenhouse', 'databricks',   'strong',  true,  'manual', 'verify slug'),
  ('Hugging Face',    'greenhouse', 'huggingface',  'strong',  true,  'manual', 'verify slug'),
  ('Character.AI',    'ashby',      'character',    'strong',  true,  'manual', 'verify slug'),
  ('Cursor',          'ashby',      'anysphere',    'strong',  true,  'manual', 'parent co Anysphere'),
  ('Glean',           'greenhouse', 'glean',        'strong',  true,  'manual', 'verify slug'),
  ('Harvey',          'ashby',      'harvey',       'strong',  true,  'manual', 'verify slug'),
  ('ElevenLabs',      'greenhouse', 'elevenlabs',   'strong',  true,  'manual', 'verify slug'),
  ('Runway',          'ashby',      'runwayml',     'strong',  true,  'manual', 'verify slug'),
  ('Replicate',       'ashby',      'replicate',    'strong',  true,  'manual', null),
  ('Together AI',     'ashby',      'togetherai',   'strong',  true,  'manual', 'verify slug'),
  ('Modal',           'ashby',      'modal',        'strong',  true,  'manual', null),
  ('LangChain',       'ashby',      'langchain',    'strong',  true,  'manual', 'verify slug'),
  ('Sierra',          'ashby',      'sierra',       'strong',  true,  'manual', 'AI agents — verify slug'),

  -- ─── Explore (broader tech + lifestyle/health) ───
  ('Airtable',        'greenhouse', 'airtable',     'explore', true,  'manual', 'verify slug'),
  ('Datadog',         'greenhouse', 'datadog',      'explore', true,  'manual', 'verify slug'),
  ('Asana',           'greenhouse', 'asana',        'explore', true,  'manual', 'verify slug'),
  ('Discord',         'greenhouse', 'discord',      'explore', true,  'manual', 'verify slug'),
  ('Strava',          'greenhouse', 'strava',       'explore', true,  'manual', 'fits active/dive interest'),
  ('Mercury',         'greenhouse', 'mercury',      'explore', true,  'manual', 'verify slug'),
  ('Mercor',          'ashby',      'mercor',       'explore', true,  'manual', 'verify slug'),
  ('Garmin',          'workday',    'wd5/garmin/External', 'explore', false, 'manual', 'Workday; Dive Apps PM target — verify site name')

on conflict (ats_type, ats_slug) do update set
  name   = excluded.name,
  tier   = excluded.tier,
  active = excluded.active,
  source = excluded.source,
  notes  = excluded.notes;
