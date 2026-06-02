# n8n Workflow Spec

Daily run that fetches job postings, scores them against the master context, and upserts to Supabase.

## Node-by-node

### 1. Cron Trigger
Daily at 09:00 UTC.

### 2. Supabase: Get active companies
```
operation: getAll
table: companies
filter: active = true
```

Branch into 3 by `ats_type`: Greenhouse, Lever, Ashby. (Workday goes to v2.)

---

### 3a. Greenhouse branch

**HTTP Request — Fetch jobs**
```
GET https://boards-api.greenhouse.io/v1/boards/{{$json.ats_slug}}/jobs?content=true
```

Response shape:
```json
{
  "jobs": [
    {
      "id": 1234567,
      "title": "Senior Product Manager, AI",
      "location": { "name": "San Francisco, CA / Remote" },
      "absolute_url": "https://boards.greenhouse.io/anthropic/jobs/1234567",
      "updated_at": "2026-05-25T18:32:00-07:00",
      "content": "<HTML-encoded job description>"
    }
  ]
}
```

**Code Node — Normalize**
```javascript
const company_id = $('Get active companies').item.json.id;
const jobs = $input.first().json.jobs || [];

return jobs.map(j => ({
  company_id,
  ats_job_id: String(j.id),
  title: j.title,
  location: j.location?.name || null,
  url: j.absolute_url,
  posted_at: j.updated_at,
  raw_jd: decodeHTMLEntities(j.content || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}));

function decodeHTMLEntities(s) {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ');
}
```

---

### 3b. Lever branch

**HTTP Request**
```
GET https://api.lever.co/v0/postings/{{$json.ats_slug}}?mode=json
```

Response shape: array of postings, each with `id`, `text` (title), `categories.location`, `hostedUrl`, `createdAt`, `descriptionPlain`.

**Code Node — Normalize**
```javascript
const company_id = $('Get active companies').item.json.id;
const jobs = $input.first().json || [];

return jobs.map(j => ({
  company_id,
  ats_job_id: j.id,
  title: j.text,
  location: j.categories?.location || null,
  url: j.hostedUrl,
  posted_at: new Date(j.createdAt).toISOString(),
  raw_jd: j.descriptionPlain || ''
}));
```

---

### 3c. Ashby branch

**HTTP Request**
```
GET https://api.ashbyhq.com/posting-api/job-board/{{$json.ats_slug}}?includeCompensation=true
```

Response shape: `{ jobs: [...] }` with each job having `id`, `title`, `locationName`, `jobUrl`, `publishedAt`, `descriptionHtml`.

**Code Node — Normalize**
```javascript
const company_id = $('Get active companies').item.json.id;
const jobs = $input.first().json.jobs || [];

return jobs.map(j => ({
  company_id,
  ats_job_id: j.id,
  title: j.title,
  location: j.locationName || null,
  url: j.jobUrl,
  posted_at: j.publishedAt,
  raw_jd: (j.descriptionHtml || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}));
```

---

### 4. Merge all branches
Use n8n's Merge node in "Append" mode to combine the three branches into one list.

### 5. Supabase: Check existing jobs
For each item, lookup `jobs` by `(company_id, ats_job_id)`.

- **Exists** → update `last_seen_at = now()`, skip scoring
- **New** → continue to scoring

### 6. Anthropic API: Score new jobs

**HTTP Request**
```
POST https://api.anthropic.com/v1/messages
Headers:
  x-api-key: {{ANTHROPIC_KEY}}
  anthropic-version: 2023-06-01
  content-type: application/json

Body:
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 400,
  "system": [
    {
      "type": "text",
      "text": "<contents of prompts/scoring-prompt.md with MASTER_CONTEXT_DOC inlined>",
      "cache_control": { "type": "ephemeral" }
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": "JOB TITLE: {{$json.title}}\nLOCATION: {{$json.location}}\n\nJOB DESCRIPTION:\n{{$json.raw_jd}}"
    }
  ]
}
```

The `cache_control` on the system prompt enables prompt caching, cutting cost ~90% on repeat calls within the cache window.

### 7. Code Node — Parse Claude output
```javascript
const item = $input.first().json;
const text = item.content[0].text;
const parsed = JSON.parse(text);
const job = $('Merge').item.json;

return {
  job,
  match: {
    score: parsed.score,
    role_fit: parsed.role_fit,
    level_fit: parsed.level_fit,
    location_fit: parsed.location_fit,
    reasoning: parsed.reasoning
  }
};
```

### 8. Supabase: Upsert job
Upsert into `jobs` on conflict `(company_id, ats_job_id)`. Set `last_seen_at = now()`.

### 9. Supabase: Upsert match
Upsert into `matches` on conflict `(job_id)`.

### 10. Final cleanup: close disappeared jobs
At end of run, set `status = 'closed'` where `last_seen_at < now() - interval '2 days'` and current status is `'open'`. The 2-day buffer absorbs transient ATS failures.

```sql
update jobs
set status = 'closed'
where status = 'open'
  and last_seen_at < now() - interval '2 days';
```

Run via a Supabase SQL Execute node at the workflow end.

## Credentials needed in n8n

1. **Supabase** — URL + `service_role` key (full access, bypasses RLS)
2. **Anthropic** — API key, used in the HTTP Request node header

## Testing

1. Disable cron, run manually once with `active = true` set on only 1 company (e.g. Anthropic)
2. Verify `jobs` and `matches` rows appear in Supabase
3. Verify reasoning quality on a sample of 5 matches
4. Tune scoring threshold and prompt if needed
5. Activate all desired companies, enable cron

## Error handling

Wrap the per-company HTTP fetch in a Try/Catch (n8n Error Trigger). On failure, log to a `fetch_errors` table or Slack and continue. One company failing should not break the whole run.
