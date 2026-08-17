-- seed.sql
-- Initial company list for the Canada Strategy / BizOps watchlist.
-- Rerun-safe via ON CONFLICT.
--
-- ats_slug format reminder:
--   greenhouse: 'anthropic'
--   ashby:      'mistral'
--   lever:      'spotify'
--   workday:    'wd5/garmin/External' (host subdomain / tenant / site)
--
-- HOW THIS LIST WAS BUILT (not guesswork): every slug below was live-checked
-- against its ATS API, and the whole ~12,500-company bundled dataset in data/
-- was scanned with scripts/filters.py to find companies with real open
-- Strategy/BizOps roles in Toronto/GTA or remote-Canada. Notes record how many
-- matching roles each company had at seed time. Companies with no match that
-- day are still included when they're worth watching daily -- the pipeline
-- re-checks every morning, so seeding a good company early costs one HTTP
-- request and catches the role the day it opens.
--
-- Tiers:
--   dream   -- top Canadian targets: strong in-house strategy/BizOps functions
--   strong  -- Canadian tech + scale-ups with real strategy/ops teams
--   explore -- Canadian consumer/retail/industrial/financial (deliberately
--              outside the tech bubble), plus global companies that genuinely
--              hire Strategy/BizOps into Toronto or remote-Canada
--
-- CAVEAT (Workday): fetch_and_score.py reads at most 100 postings per Workday
-- tenant. Very large tenants (Cisco, Manulife, Magna, Brookfield...) may bury a
-- Toronto strategy role past that cap, so treat those rows as best-effort.

insert into companies (name, ats_type, ats_slug, tier, active, source, notes) values
  --  Dream: top Canadian Strategy / BizOps targets
  ('Clutch', 'greenhouse', 'clutch', 'dream', true, 'manual', 'Toronto used-car marketplace; dedicated Strategy & Ops team; 4 live matches at seed time'),
  ('DoorDash Canada', 'greenhouse', 'doordashcanada', 'dream', true, 'manual', 'dedicated Canada Strategy & Operations team, Toronto; 8 live matches at seed time'),
  ('Interac', 'workday', 'wd3/interac/interac', 'dream', true, 'manual', 'Toronto payments network; strategy & ops function; 4 live matches at seed time'),
  ('BDC', 'workday', 'wd10/bdc/bdc_careers', 'dream', true, 'manual', 'Business Development Bank of Canada; business strategy advisory; 4 live matches at seed time'),
  ('Momentum Financial Services', 'greenhouse', 'momentumfinancialservicesgroup', 'dream', true, 'manual', 'Toronto consumer finance; strategy + product strategy roles; 1 live match at seed time'),
  ('Relay', 'ashby', 'relayfi', 'dream', true, 'manual', 'Toronto fintech; strategic ops + product ops; 2 live matches at seed time'),
  ('Venn', 'ashby', 'venn', 'dream', true, 'manual', 'Toronto; GTM strategy & ops; 2 live matches at seed time'),
  ('Wealthsimple', 'ashby', 'wealthsimple', 'dream', true, 'manual', 'Toronto fintech; strong BizOps bench'),
  ('Trulioo', 'ashby', 'trulioo', 'dream', true, 'manual', 'former employer; Vancouver-HQ but posts remote-Canada'),
  ('Lightspeed Commerce', 'ashby', 'lightspeedhq', 'dream', true, 'manual', 'Montreal-HQ; posts Strategy Manager/Analyst roles in Toronto; 2 live matches at seed time'),
  ('Ontario Teachers'' Pension Plan', 'workday', 'wd3/otppb/ontarioteachers_careers', 'dream', true, 'manual', 'Toronto; premier in-house strategy shop'),
  ('OMERS', 'workday', 'wd3/omers/omers_external', 'dream', true, 'manual', 'Toronto pension; corporate strategy'),
  ('CDPQ', 'workday', 'wd10/cdpq/cdpq', 'dream', true, 'manual', 'Quebec pension; strategy + corp dev'),
  ('HOOPP', 'workday', 'wd10/hoopp/hoopp', 'dream', true, 'manual', 'Toronto pension; strategy roles'),
  --  Strong: Canadian tech + scale-ups
  ('1Password', 'ashby', '1password', 'strong', true, 'manual', 'Toronto; revenue strategy/ops'),
  ('Jobber', 'ashby', 'jobber', 'strong', true, 'manual', 'Edmonton-HQ, posts Toronto/remote-Canada'),
  ('Benevity', 'ashby', 'benevity', 'strong', true, 'manual', 'Calgary-HQ; remote-Canada BizOps'),
  ('KOHO', 'ashby', 'koho', 'strong', true, 'manual', 'Toronto fintech'),
  ('Neo Financial', 'ashby', 'neofinancial', 'strong', true, 'manual', 'Calgary fintech; large board'),
  ('Float', 'ashby', 'float', 'strong', true, 'manual', 'Toronto fintech'),
  ('Docebo', 'ashby', 'docebo', 'strong', true, 'manual', 'Toronto SaaS'),
  ('Loopio', 'ashby', 'loopio', 'strong', true, 'manual', 'Toronto SaaS'),
  ('Klue', 'ashby', 'klue', 'strong', true, 'manual', 'Vancouver; competitive intelligence'),
  ('Miovision', 'ashby', 'miovision', 'strong', true, 'manual', 'Kitchener; posts Ontario roles'),
  ('Rewind', 'ashby', 'rewind', 'strong', true, 'manual', 'Ottawa SaaS'),
  ('Solink', 'ashby', 'solink', 'strong', true, 'manual', 'Ottawa'),
  ('Top Hat', 'ashby', 'top-hat', 'strong', true, 'manual', 'Toronto edtech'),
  ('Thinkific', 'ashby', 'thinkific', 'strong', true, 'manual', 'Vancouver; remote-Canada'),
  ('Hopper', 'ashby', 'hopper', 'strong', true, 'manual', 'Montreal travel'),
  ('Maple', 'ashby', 'maple', 'strong', true, 'manual', 'Toronto virtual healthcare'),
  ('Bree', 'ashby', 'bree', 'strong', true, 'manual', 'Toronto fintech; Strategy & Ops team; 1 live match at seed time'),
  ('Valence', 'ashby', 'jobs-valence', 'strong', true, 'manual', 'Toronto/NY; Strategy & Ops associate; 1 live match at seed time'),
  ('FacilityOS', 'ashby', 'facilityos', 'strong', true, 'manual', 'Toronto; revenue operations analytics; 1 live match at seed time'),
  ('Jane', 'ashby', 'jane', 'strong', true, 'manual', 'Canadian health-practice software; growth strategy'),
  ('Nuclear Promise X', 'ashby', 'npx', 'strong', true, 'manual', 'Canadian nuclear-sector consultancy; niche strategy work; 1 live match at seed time'),
  ('Cohere', 'ashby', 'cohere', 'strong', true, 'manual', 'Toronto AI lab; RevOps roles listed in Toronto; 1 live match at seed time'),
  ('StackAdapt', 'greenhouse', 'stackadapt', 'strong', true, 'manual', 'Toronto adtech; large board'),
  ('Coveo', 'greenhouse', 'coveoen', 'strong', true, 'manual', 'Quebec SaaS'),
  ('League', 'greenhouse', 'leagueinc', 'strong', true, 'manual', 'Toronto health benefits platform'),
  ('AlayaCare', 'greenhouse', 'alayacare', 'strong', true, 'manual', 'Montreal homecare software'),
  ('D2L', 'greenhouse', 'd2l', 'strong', true, 'manual', 'Kitchener edtech'),
  ('Flipp', 'greenhouse', 'flipp', 'strong', true, 'manual', 'Toronto retail tech'),
  ('Hootsuite', 'greenhouse', 'hootsuite', 'strong', true, 'manual', 'Vancouver; remote-Canada roles'),
  ('7shifts', 'greenhouse', '7shifts', 'strong', true, 'manual', 'Saskatoon; restaurant workforce SaaS'),
  ('Workleap', 'greenhouse', 'workleap', 'strong', true, 'manual', 'Montreal SaaS'),
  ('CoLab Software', 'greenhouse', 'colabsoftware', 'strong', true, 'manual', 'St. John''s NL engineering SaaS'),
  ('Visier', 'greenhouse', 'visiersolutionsinc', 'strong', true, 'manual', 'Vancouver people analytics'),
  ('Tenstorrent', 'greenhouse', 'tenstorrent', 'strong', true, 'manual', 'Toronto semiconductor'),
  ('Konrad Group', 'greenhouse', 'konradgroup', 'strong', true, 'manual', 'Toronto digital consultancy'),
  ('Pine', 'greenhouse', 'pine', 'strong', true, 'manual', 'Toronto mortgage fintech; BizOps analyst hiring; 1 live match at seed time'),
  ('Trolley', 'greenhouse', 'trolley', 'strong', true, 'manual', 'Toronto payouts fintech; 1 live match at seed time'),
  ('Roofr', 'greenhouse', 'roofr', 'strong', true, 'manual', 'remote-Canada RevOps hiring; 1 live match at seed time'),
  ('PointClickCare', 'lever', 'pointclickcare', 'strong', true, 'manual', 'Mississauga healthcare SaaS; large board'),
  ('Wave HQ', 'lever', 'waveapps', 'strong', true, 'manual', 'Toronto SMB fintech'),
  ('Achievers', 'lever', 'achievers', 'strong', true, 'manual', 'Toronto employee engagement'),
  ('BenchSci', 'lever', 'benchsci', 'strong', true, 'manual', 'Toronto AI biotech'),
  ('Waabi', 'lever', 'waabi', 'strong', true, 'manual', 'Toronto autonomous trucking'),
  ('Caseware', 'lever', 'caseware', 'strong', true, 'manual', 'Toronto audit software'),
  ('Zensurance', 'lever', 'zensurance', 'strong', true, 'manual', 'Toronto insurtech'),
  ('ShyftLabs', 'lever', 'shyftlabs', 'strong', true, 'manual', 'Toronto data consultancy'),
  ('Optimus SBR', 'lever', 'optimussbr', 'strong', true, 'manual', 'Toronto management consultancy; corp dev analyst track; 1 live match at seed time'),
  ('Emburse', 'lever', 'emburse', 'strong', true, 'manual', 'Toronto; product operations; 1 live match at seed time'),
  ('Magnet Forensics', 'lever', 'magnetforensics', 'strong', true, 'manual', 'Waterloo; product operations'),
  ('EQ Bank', 'lever', 'eqbank', 'strong', true, 'manual', 'Toronto challenger bank'),
  ('Potloc', 'lever', 'Potloc', 'strong', true, 'manual', 'Montreal market-research startup; consulting-adjacent'),
  ('Clio', 'workday', 'wd3/clio/cliocareersite', 'strong', true, 'manual', 'Burnaby legal SaaS; 2 live matches at seed time'),
  ('Arctic Wolf', 'workday', 'wd1/arcticwolf/external', 'strong', true, 'manual', 'Waterloo cybersecurity'),
  ('SOTI', 'workday', 'wd3/soti/careers', 'strong', true, 'manual', 'Mississauga; sales-ops analytics; 2 live matches at seed time'),
  --  Explore: Canadian consumer/retail/industrial/financial + global cos hiring into Toronto
  ('Mejuri', 'greenhouse', 'mejuri', 'explore', true, 'manual', 'Toronto DTC jewellery; large board'),
  ('Indigo', 'greenhouse', 'indigo', 'explore', true, 'manual', 'Toronto book retail'),
  ('Kensington Tours', 'greenhouse', 'kensingtontours', 'explore', true, 'manual', 'Toronto luxury travel; hires Corp Dev & Strategy'),
  ('Knix', 'lever', 'knix', 'explore', true, 'manual', 'Toronto DTC apparel'),
  ('Wattpad WEBTOON', 'lever', 'wattpad', 'explore', true, 'manual', 'Toronto digital storytelling'),
  ('LCBO', 'workday', 'wd3/lcbo/lcbocareersite', 'explore', true, 'manual', 'Ontario Crown retailer; strategy + merchandising ops'),
  ('Aritzia', 'workday', 'wd3/aritzia/external', 'explore', true, 'manual', 'Vancouver fashion retail; posts Toronto roles'),
  ('Canada Goose', 'workday', 'wd3/canadagoose/canadagoosecareers', 'explore', true, 'manual', 'Toronto apparel'),
  ('Cineplex', 'workday', 'wd3/cineplex/cineplex', 'explore', true, 'manual', 'Toronto entertainment'),
  ('Moneris', 'workday', 'wd3/moneris/moneris', 'explore', true, 'manual', 'Toronto payments'),
  ('RBC', 'workday', 'wd3/rbc/rbcearlytalent1', 'explore', true, 'manual', 'early-talent board; Toronto strategy analyst roles; 4 live matches at seed time'),
  ('Sun Life', 'workday', 'wd3/sunlife/experienced-jobs', 'explore', true, 'manual', 'Toronto insurer; strategy analyst roles; 1 live match at seed time'),
  ('Manulife', 'workday', 'wd3/manulife/mfcjh_jobs', 'explore', true, 'manual', 'Toronto insurer'),
  ('Intact Financial', 'workday', 'wd3/intactfc/intactfc', 'explore', true, 'manual', 'Toronto insurer'),
  ('Magna', 'workday', 'wd3/magna/magna', 'explore', true, 'manual', 'Aurora ON auto parts'),
  ('CAE', 'workday', 'wd3/cae/career', 'explore', true, 'manual', 'Montreal flight simulation'),
  ('Enbridge', 'workday', 'wd3/enbridge/enbridge_careers', 'explore', true, 'manual', 'Calgary energy infrastructure'),
  ('Suncor', 'workday', 'wd1/suncor/suncor_external', 'explore', true, 'manual', 'Calgary energy'),
  ('Cenovus', 'workday', 'wd3/cenovus/careers', 'explore', true, 'manual', 'Calgary energy'),
  ('Brookfield', 'workday', 'wd5/brookfield/brookfield', 'explore', true, 'manual', 'Toronto alt-asset manager; strong strategy/corp dev'),
  ('Thomson Reuters', 'workday', 'wd5/thomsonreuters/external_career_site', 'explore', true, 'manual', 'Toronto info services; 1 live match at seed time'),
  ('Otter', 'greenhouse', 'otter', 'explore', true, 'manual', 'hires sales ops into Toronto; 1 live match at seed time'),
  ('Kepler Group', 'greenhouse', 'keplergroup', 'explore', true, 'manual', 'hires strategy into Toronto; 1 live match at seed time'),
  ('Tripledot Studios', 'greenhouse', 'tripledotstudios', 'explore', true, 'manual', 'hires strategy into Toronto; 1 live match at seed time'),
  ('FanDuel', 'greenhouse', 'fanduel', 'explore', true, 'manual', 'hires acquisition strategy into Toronto; 1 live match at seed time'),
  ('Zynga', 'greenhouse', 'zyngacareers', 'explore', true, 'manual', 'Toronto BizOps; 1 live match at seed time'),
  ('HubSpot', 'greenhouse', 'hubspotjobs', 'explore', true, 'manual', 'remote-Ontario pricing strategy; 1 live match at seed time'),
  ('Instacart', 'greenhouse', 'instacart', 'explore', true, 'manual', 'remote-Canada RevOps'),
  ('Okta', 'greenhouse', 'okta', 'explore', true, 'manual', 'hires product ops into Toronto'),
  ('Samsara', 'greenhouse', 'samsara', 'explore', true, 'manual', 'remote-Toronto BizOps; 1 live match at seed time'),
  ('Elastic', 'greenhouse', 'elastic', 'explore', true, 'manual', 'Canada RevOps'),
  ('Cision', 'greenhouse', 'cision', 'explore', true, 'manual', 'Canada sales ops; 1 live match at seed time'),
  ('Cloudflare', 'greenhouse', 'cloudflare', 'explore', true, 'manual', 'hires strategy roles; 1 live match at seed time'),
  ('Stripe', 'greenhouse', 'stripe', 'explore', true, 'manual', 'large board; remote strategy roles; 1 live match at seed time'),
  ('Decagon', 'ashby', 'decagon', 'explore', true, 'manual', 'hires strategy into Toronto; 1 live match at seed time'),
  ('EliseAI', 'ashby', 'eliseai', 'explore', true, 'manual', 'NYC/Toronto product strategy & ops; 1 live match at seed time'),
  ('Homebase', 'ashby', 'homebase', 'explore', true, 'manual', 'Toronto RevOps; 1 live match at seed time'),
  ('Litmus', 'ashby', 'litmus', 'explore', true, 'manual', 'Toronto GTM/RevOps; 1 live match at seed time'),
  ('Directive', 'ashby', 'directive', 'explore', true, 'manual', 'remote-Canada RevOps'),
  ('Zip', 'ashby', 'zip', 'explore', true, 'manual', 'Toronto GTM strategy & ops; 1 live match at seed time'),
  ('Warner Music Group', 'lever', 'wmg', 'explore', true, 'manual', 'Toronto business operations; 1 live match at seed time'),
  ('YETI', 'workday', 'wd5/yeticoolers/yeti', 'explore', true, 'manual', 'Toronto commercial ops; 1 live match at seed time'),
  ('Guidewire', 'workday', 'wd5/guidewire/external', 'explore', true, 'manual', 'Mississauga business ops; 1 live match at seed time'),
  ('Salesforce', 'workday', 'wd12/salesforce/external_career_site', 'explore', true, 'manual', 'corp dev M&A integration; 1 live match at seed time'),
  ('Adobe', 'workday', 'wd5/adobe/external_experienced', 'explore', true, 'manual', 'strategy and operations'),
  ('Cisco', 'workday', 'wd5/cisco/cisco_careers', 'explore', true, 'manual', 'pricing & strategy; 1 live match at seed time'),
  ('Zendesk', 'workday', 'wd1/zendesk/zendesk', 'explore', true, 'manual', 'sales operations; 3 live matches at seed time'),
  --  Board responds but currently lists no postings -- seeded inactive
  ('Coconut Software', 'greenhouse', 'coconutsoftware', 'explore', false, 'manual', 'board responds but returns 0 postings; re-enable if they resume hiring'),
  ('Unbounce', 'greenhouse', 'unbounce', 'explore', false, 'manual', 'board responds but returns 0 postings; re-enable if they resume hiring'),
  --  Carried over from the previous US AI/product seed (demoted to explore)
  ('Anthropic', 'greenhouse', 'anthropic', 'explore', true, 'manual', 'carried over from previous seed'),
  ('OpenAI', 'ashby', 'openai', 'explore', true, 'manual', 'carried over from previous seed'),
  ('NVIDIA', 'workday', 'wd5/nvidia/nvidiaexternalcareersite', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Mistral', 'ashby', 'mistral', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Notion', 'ashby', 'notion', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Figma', 'greenhouse', 'figma', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Vercel', 'greenhouse', 'vercel', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Linear', 'ashby', 'linear', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Ramp', 'ashby', 'ramp', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Perplexity', 'ashby', 'perplexity', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Scale AI', 'greenhouse', 'scaleai', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Databricks', 'greenhouse', 'databricks', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Character.AI', 'ashby', 'character', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Cursor', 'ashby', 'cursor', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Glean', 'greenhouse', 'gleanwork', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Harvey', 'ashby', 'harvey', 'explore', true, 'manual', 'carried over from previous seed'),
  ('ElevenLabs', 'ashby', 'elevenlabs', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Runway', 'ashby', 'runway-ml', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Replicate', 'ashby', 'replicate', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Together AI', 'greenhouse', 'togetherai', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Modal', 'ashby', 'modal', 'explore', true, 'manual', 'carried over from previous seed'),
  ('LangChain', 'ashby', 'langchain', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Sierra', 'ashby', 'sierra', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Airtable', 'greenhouse', 'airtable', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Datadog', 'greenhouse', 'datadog', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Asana', 'greenhouse', 'asana', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Discord', 'greenhouse', 'discord', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Strava', 'ashby', 'strava', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Mercury', 'greenhouse', 'mercury', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Mercor', 'ashby', 'mercor', 'explore', true, 'manual', 'carried over from previous seed'),
  ('Google DeepMind', 'workday', 'wd5/google/External', 'explore', false, 'manual', 'Google uses a custom careers site, not myworkdayjobs.com — left inactive'),
  ('Hugging Face', 'greenhouse', 'huggingface', 'explore', false, 'manual', 'actually on Workable, which this pipeline does not support — left inactive'),
  ('Garmin', 'workday', 'wd5/garmin/External', 'explore', false, 'manual', 'actually on iCIMS, which this pipeline does not support — left inactive')

on conflict (ats_type, ats_slug) do update set
  name   = excluded.name,
  tier   = excluded.tier,
  active = excluded.active,
  source = excluded.source,
  notes  = excluded.notes;
