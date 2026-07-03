# Wohnheim Finder

Automated lead collection, categorization, and draft generation for student-residence outreach.

This project is built for manual-control outreach: it can discover and categorize residences, generate initial emails and 3-day follow-ups, and show everything in a local review dashboard. It does **not** silently send mail. You approve, export, mark sent, or explicitly send each message.

## What It Does

- Imports seeded Munich/Garching/Freising/Rosenheim student-residence findings.
- Scrapes configured source pages for additional candidate links/headings.
- Classifies leads into categories such as public student union, Catholic, Protestant, ecumenical Christian, nonprofit/foundation, municipal, commercial private, specialized, and short-term fallback.
- Generates German outreach drafts from your truthful profile.
- Generates follow-up drafts every 3 days after a message is marked sent.
- Exports `.eml` files or sends via SMTP only after dashboard approval and a typed `SEND` confirmation.
- Supports `wohnheim stop` so you can pause follow-up generation.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config/applicant.example.yaml config/applicant.yaml
```

Edit `config/applicant.yaml` with your real facts. Do not put claims in that file unless you can honestly explain or prove them.

Optional AI generation:

```bash
cp .env.example .env
# Fill DEEPSEEK_API_KEY in .env if you want AI-generated variants.
```

Optional SMTP sending from the dashboard:

```bash
# Fill SMTP_* fields in .env.
# Gmail usually requires an app password, not your normal account password.
```

## Run

```bash
wohnheim discover
wohnheim list
wohnheim generate-drafts
wohnheim serve
```

Open the dashboard at:

```text
http://127.0.0.1:8765
```

Dashboard controls:

- `Approve`: approve the draft for possible sending.
- `Download .eml`: open/send manually in Apple Mail, Gmail, etc.
- `Mark sent`: record that you sent it manually, enabling future follow-ups.
- `SMTP Send`: sends only if the draft is approved, SMTP is configured, and you type `SEND`.
- `Stop/pause follow-ups`: prevents new follow-up drafts.

AI-generated drafts:

```bash
wohnheim generate-drafts --ai
```

This loads `.env` automatically and prefers DeepSeek:

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

The current DeepSeek API is OpenAI-compatible. As of 2026-07-03, DeepSeek's official docs list `deepseek-v4-flash` and `deepseek-v4-pro` as current models, while `deepseek-chat` and `deepseek-reasoner` are marked for deprecation on 2026-07-24.

Fallback precedence is:

1. `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`
2. `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`
3. `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`

The prompt instructs the model to use only facts from `config/applicant.yaml`; missing facts become placeholders.

## Weekly Category Campaigns

Use this when you want one base mail for the week, then one tailored mail per residence category. The same category mail is used for every dorm in that category.

```bash
wohnheim generate-weekly-campaign --ai
wohnheim serve
```

This creates:

- one timestamped weekly base mail in `campaigns/<ISO-week>/<timestamp>/base/base-mail.md`
- one tailored category mail per active category in `campaigns/<ISO-week>/<timestamp>/categories/`
- dashboard drafts for every active residence
- `.eml` files under `outbox/<ISO-week>/<timestamp>/<category>/` for residences with email addresses

The weekly base mail uses the last two saved base mails as context, so the AI has continuity from previous weeks. The category mails are generated from the weekly base mail plus the category profile. They intentionally do not mention a specific dorm name, because the same text is reused for every dorm in that category.

To only save the base/category mails without creating dashboard drafts:

```bash
wohnheim generate-weekly-campaign --ai --no-drafts
```

To generate only one category:

```bash
wohnheim generate-weekly-campaign --ai --category catholic_church
```

Generated `campaigns/`, `outbox/`, and `data/outreach.sqlite` files are ignored by Git because they can contain private applicant details.

## Follow-Up Logic

Initial drafts are created for active residences with no prior message.

Follow-up drafts are created only when:

- a previous message is marked `sent`, and
- at least 3 days have passed, or the value passed through `--follow-up-days`.

Examples:

```bash
wohnheim mark-sent 12
wohnheim generate-drafts --follow-up-days 3
wohnheim stop
wohnheim resume
```

## Strong Truthful Angles

Use these only when accurate:

- Financial pressure: you cannot sustainably pay Munich market rent and need a student-priced place.
- Current housing ending: your current lease/sublet/temporary stay ends on a specific date.
- No stable local fallback: you do not have family housing or a long-term place near Munich.
- Study continuity: housing instability affects lectures, exams, commuting time, and concentration.
- Immediate readiness: you can send documents today and accept a room quickly.
- Flexibility: you accept smaller rooms, shared kitchens, temporary offers, Nachrücken, or waiting-list spots.
- Community fit: for Christian/ecumenical houses, you are willing to participate respectfully in house life and submit a motivation letter or reference if required.
- Hardship route: ask whether there is a Härtefall-, Nachrück-, or emergency process, but only describe hardship facts that are true.

Do not say you are being kicked out unless that is actually happening. Use precise wording instead, for example:

```text
Meine aktuelle Zwischenmiete endet am [Datum], und ich habe danach noch keine langfristig gesicherte Unterkunft.
```

or:

```text
Ich kann die aktuellen WG-/Apartmentpreise in München mit meinem studentischen Budget nicht dauerhaft tragen.
```

## Source Strategy

The seeded file `data/seed_residences.csv` starts with Munich-area sources because that is the highest-probability target for a TUM student. It is not a legal guarantee that every residence exists in the file forever; housing pages change. Re-run discovery and add more source URLs in `config/sources.yaml` to expand coverage.

Initial source surfaces include:

- Studierendenwerk München Oberbayern public residences.
- Studierendenwerk private-carrier list.
- TUM church/social carrier list.
- Erzbistum München Catholic residence overview.
- Evangelische Studentenwohnheime München e.V.
- JIZ Munich accommodation guide.
- Commercial provider pages found during current research.

## Data Files

- `config/sources.yaml`: source pages and seed file path.
- `config/applicant.yaml`: your private, truthful profile. This is intentionally ignored until you create it.
- `data/seed_residences.csv`: current seed findings.
- `data/outreach.sqlite`: generated database, ignored by Git.
- `campaigns/`: generated weekly base and category mails, ignored by Git.
- `outbox/*.eml`: generated message files, ignored by Git.

## Useful Commands

```bash
wohnheim categories
wohnheim discover --no-fetch
wohnheim list --all
wohnheim messages
wohnheim messages --status draft
wohnheim generate-drafts --limit 10
wohnheim generate-weekly-campaign --ai
wohnheim generate-weekly-campaign --ai --no-drafts
wohnheim serve --port 8766
```
