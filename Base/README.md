# Typst CV + Letter system — agent contract

Deterministic, vision-free tailoring. The template owns **all** layout, fonts,
margins and spacing. An agent only writes plain text into two YAML files; if the
text is too long the compile **fails loud** with a fixable message. There is no
visual balancing to do — Typst spacing is fixed, so the Canva "box grew and ate
the gap" failure mode cannot happen.

## To tailor for a new role

1. `mkdir Applications/<Company>-<Role-Slug>/`
2. Copy the two YAML files from any existing application as a starting point:
   - `cv-data.yaml`
   - `letter-data.yaml`
3. Edit **only the text** in those two files for the new role (see schema below).
4. Build:
   ```powershell
   ./Base/build.ps1 -App "<Company>-<Role-Slug>"
   ```
5. If it fails, read the assertion message, shorten the offending field, rebuild.
   Repeat until it prints `OK`. Outputs: `cv.pdf`, `motivation-letter.pdf`.

## What you may edit (YAML only)

`cv-data.yaml`
| Field | Notes / guard-rail |
|---|---|
| `variant` | `grotesk_one_page` (default for new marketing drafts), `compact_one_page`, `classic_two_page`, or `enriched_two_page` |
| `role_focus` | optional builder hint: `marketing`, `content`, `brand`, `community`, or `commercial_ops` |
| `title` | role-target line under the name |
| `tagline` | one sentence, ≤ 170 chars |
| `profile` | summary paragraph, ≤ 600 chars |
| `selected_highlights[]` | optional scan-friendly proof points, max 4, ≤ 135 chars each |
| `experience[]` | `role, company, period, location, include, bullets[]` |
| `additional[]` | same shape; compact CVs render these as condensed earlier experience |
| `max_pages` | `1` for `grotesk_one_page` and `compact_one_page`, `2` for two-page variants |

`letter-data.yaml`
| Field | Notes / guard-rail |
|---|---|
| `subtitle` | "Role — Company" under the name |
| `paragraphs[]` | 3–5 paragraphs, body ≤ ~2050 chars (1 page) |
| `max_pages` | default 1 |

Per bullet: **≤ 5 bullets per role**, **≤ ~165 chars each** (≈ 2 lines).
Use `~` for "approximately" and `—` (em dash) freely.

### CV variants

New dashboard-generated marketing/content/brand/community drafts default to
**`grotesk_one_page`**. This is the definitive starting template for future
tailoring: a compact one-page CV with all proof under a single Experience
heading. Existing YAML files without `variant` remain backward-compatible:
`max_pages: 2` renders as the old `classic_two_page` layout, while
`max_pages: 1` renders compact.

- `grotesk_one_page` — compact-derived one-page marketing CV with Summary,
  Experience, Education, Skills, Languages, and Certifications. It renders no
  Selected Impact, Additional Experience, Other, or References sections.
- `compact_one_page` — compact sidebar, profile, optional selected impact,
  primary experience, and condensed earlier experience.
- `classic_two_page` — legacy structure: page 1 profile/experience, page 2
  certifications/additional experience.
- `enriched_two_page` — two-page variant that can also surface selected impact
  on page 2 when extra proof is useful.

### Experience ordering for marketing-target roles

For roles in Candidate Name's target categories (Marketing, Campaign Manager, Content
Creator, Content Coordinator, Brand, Community, and similar), use
`grotesk_one_page` and put all rendered roles in `experience[]`.

Marketing-focused Grotesk CVs must include:
- **Marketing Operations Assistant — Belkin B.V.**
- **Curatorial & Marketing Assistant — Victory Art Rotterdam**

Do not create an Additional Experience section for a single role. If legacy YAML
still has Belkin or Victory Art in `additional[]`, the dashboard normalizes them
into `experience[]` when the draft is read or saved.

## Frozen — never tailored, lives in `Base/`

Name, contact, core skills, languages, education, certifications, the greeting
/ sign-off / signature, and every colour, font, size and margin. To change any
of these, edit the template (`cv.typ`, `letter.typ`, `lib.typ`) once — it
propagates to every application.

Contact entries can carry a clickable `url:` (Email → mailto, LinkedIn, ISSUU
portfolio); linked values render in the accent colour. These live in the
`CONTACT` block in `cv.typ`.

The default frozen `SKILLS` bank in `cv.typ` is now a planning-oriented
marketing baseline (`SKILLS_MARKETING_PLANNING`) for coordinator, planning,
operations, and analytics-heavy applications. For one-page variants, ordering
matters: the first **8** skills render. Keep the strongest cross-role proof
points first.

Languages are also frozen in `cv.typ`. One-page variants render **4** language
entries, so proficiency updates there propagate automatically. Current frozen
levels include `Spanish: Intermediate`.

## Chameleon brand theme (auto-generated — never hand-edited)

`Applications/<App>/brand-theme.yaml` is written by the Chameleon scraper
(`jobhunt/brand_theme.py`, `jobhunt/font_theme.py`) via the dashboard, never by
an agent tailoring `cv-data.yaml`/`letter-data.yaml`. It is **opt-in per
application**: colors and fonts only apply when `enabled: true`, and custom
fonts/weights only apply when the user has separately toggled
`typography_enabled: true` for that application. When present and enabled, the
theme can set:

| Field | Applies to |
|---|---|
| `body_font` | body text tier — profile, bullets, contact/sidebar |
| `heading_font` | heading + subheading tiers (section titles, name, role/company lines) |
| `body_weight` | body text tier |
| `subheading_weight` | subheading tier — role/company lines |
| `heading_weight` | heading tier — section titles ("EXPERIENCE", "SKILLS", …) and the name |

If any of these keys are absent — including every application predating this
feature — `lib.typ` falls back to the historical defaults (Segoe UI/Roboto,
bold section titles, bold role lines, regular body) with no visual change. A
user can always disable `typography_enabled` to fall back to the original CV
font, regardless of what Chameleon extracted.

## Files
- `lib.typ` — design tokens, components, guard-rail asserts
- `cv.typ` — CV layout + Candidate Name's frozen sidebar facts
- `letter.typ` — letter layout + frozen greeting/signature
- `assets/signature.png` — handwritten signature
- `build.ps1` — compile one application, exit non-zero on any failure
