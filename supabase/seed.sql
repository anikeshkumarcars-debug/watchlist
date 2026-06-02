-- seed.sql
-- Inserts the initial company list. Rerun-safe via ON CONFLICT.
-- Update this whenever companies.json changes, then run in Supabase SQL editor.

insert into companies (name, ats_type, ats_slug, tier, active, notes) values
  ('Anthropic',       'greenhouse', 'anthropic',  'dream',   true,  'AI safety lab'),
  ('OpenAI',          'greenhouse', 'openai',     'dream',   true,  'Verify slug'),
  ('Google DeepMind', 'workday',    'google',     'dream',   false, 'Workday; v2'),
  ('NVIDIA',          'workday',    'nvidia',     'dream',   false, 'Workday; v2'),
  ('Stripe',          'greenhouse', 'stripe',     'strong',  true,  null),
  ('Notion',          'greenhouse', 'notion',     'strong',  true,  'Verify slug'),
  ('Figma',           'greenhouse', 'figma',      'strong',  true,  'Verify slug'),
  ('Vercel',          'greenhouse', 'vercel',     'strong',  true,  'Verify slug'),
  ('Linear',          'ashby',      'linear',     'strong',  true,  null),
  ('Ramp',            'ashby',      'ramp',       'strong',  true,  null),
  ('Perplexity',      'ashby',      'perplexity', 'strong',  true,  'Verify slug and ATS'),
  ('Scale AI',        'greenhouse', 'scaleai',    'strong',  true,  'Verify slug'),
  ('Databricks',      'greenhouse', 'databricks', 'strong',  true,  'Verify slug'),
  ('Hugging Face',    'greenhouse', 'huggingface','strong',  true,  'Verify slug'),
  ('Airtable',        'greenhouse', 'airtable',   'explore', true,  'Verify slug'),
  ('Datadog',         'greenhouse', 'datadog',    'explore', true,  'Verify slug'),
  ('Asana',           'greenhouse', 'asana',      'explore', true,  'Verify slug'),
  ('Garmin',          'workday',    'garmin',     'explore', false, 'Workday; Dive Apps PM target; v2')
on conflict (ats_type, ats_slug) do update set
  name = excluded.name,
  tier = excluded.tier,
  active = excluded.active,
  notes = excluded.notes;
