---
name: symphony-design
description: Enforces Symphony's brand identity on every UI change and every piece of user-facing copy in this repo. Provides design tokens (colours, typography), logo rules, voice and tone principles, and a mandatory publish checklist. Use when editing any file under frontend/, any .tsx/.ts/.css/.scss file, any backend string that reaches end users (error messages, notifications, email copy), or any end-user-facing documentation. Skip only for pure backend logic that never produces user-visible text.
---

# Symphony Design System

Read this skill fully before editing any UI or user-facing text.

## Design tokens

Source of truth: `frontend/src/theme/tokens.ts`. Never hardcode hex values in components.

### Colours

Core palette:

- `primary` purple `#6c69ff` — brand accent, links, active states.
- `red` `#fe7475` — error state accent. Never text.
- `yellow` `#ffbe3d` — warning/attention accent. Never text.
- `lightGrey` `#f4f5fb` — surface backgrounds.
- `black` `#000000` — text.
- `white` `#ffffff` — text, surfaces.

Secondary palette (accents only, never text):

- `navy` `#222453`
- `lightBlue` `#91afea`
- `blueGrey` `#9fabc0`
- `peach` `#f9dfc4`

Hard rules:

- Text is only ever `black` or `white`.
- Secondary colours are for accents, shapes, and charts. Not primary surfaces. Never text.
- Status mapping: success uses `primary`, warning uses `yellow`, error uses `red`. KPI highlights follow the same mapping.

### Typography

Font: Poppins, self-hosted in `frontend/src/assets/fonts/`. Never load from a third-party CDN.

- H1: Bold 72
- H2: Bold 48
- H3: SemiBold 36
- H4: Medium 30
- Body: Regular 16, line-height 23, tracking 10 (optical kerning)
- Tag: Bold 20
- CTA: Bold 30

## Logo and iconography

Assets live at `frontend/src/assets/brand/`. Primary, secondary (compact), one-colour variants.

- Safety area: minimum 1/2 of the logo's x-height on every side.
- On `primary` purple: use white logo. Black only as fallback when design constraints make white impossible.
- Do not crop, distort, rotate, recolour, resize parts, add shadow, add gradient.
- Favicon uses the Symphony mark only.
- Shapes: minimal geometric shapes, solid or stroke, never mixed in a single composition. Use as chart decorations, dividers, or list markers.

## Voice and tone

Four pillars — every sentence reflects all four:

1. **Precise** — name things. Use specific words. Use real numbers.
2. **Direct** — lead with the point. First sentence carries the weight.
3. **Human** — "we" and "you". Active voice. Warm.
4. **Confident** — no hedging. Make the claim, then support it.

### Words Symphony owns

AI-native, engineer, engineering, playbook, partnership, live, measurable, precision, precise, ambitious.

### Words Symphony avoids

`leverage` (as verb), `synergy`, `cutting-edge`, `best-in-class`, `world-class`, `solutions` (as noun for products), `empower`, `unleash`, `holistic`, `resources` (when referring to people).

### Mechanics

- Active voice. "We rebuilt the pipeline", not "The pipeline was rebuilt".
- Oxford comma always.
- Numerals for metrics. `40 engineers`, `60% faster`, `3 weeks`.
- Em dashes allowed (one per paragraph). Use a real em dash `—`, never `--`.
- Write in first person plural (`we`) when referring to Symphony internally. Third person only when Symphony speaks about itself externally (marketing copy, case studies).

## Before you publish (mandatory checklist)

Every PR that changes UI or user-facing text must answer yes to all five:

1. Is it specific? Replace "Symphony" with any other company name. If the sentence still works, rewrite it.
2. Does it lead with the point? The most important sentence must be in the first two.
3. Would a senior engineer be proud to say this? Cut anything hollow.
4. Who is doing the thing? Find every passive construction. Name the subject.
5. Does it sound like us? Read aloud. If it sounds like a press release, start over.

## Context-specific tone

- Empty states: human, brief. `No hires yet for this period.`
- Error messages: specific and actionable. State what failed and what to try.
- Confirmation dialogs: direct, name the action. `Remove Enis Kudo from admins?`
- Button labels: verb-first, short. `Save changes`, `Refresh`, `Add user`. Not `Submit` or `OK`.
- Tooltips: one fragment or one short sentence.
- Audit log entries: neutral, factual. `aida.jugo@symphony.is changed role of enis.kudo@symphony.is from viewer to admin.`

## Anti-patterns

- Hardcoded `#6c69ff` or any hex in a component. Import from `tokens.ts`.
- Any colour other than `black` or `white` used for text.
- Secondary colours used as surfaces or body text.
- Emoji in UI chrome (buttons, labels, navigation). Emoji allowed only when a copy requirement explicitly calls for them.
- Marketing language: `cutting-edge`, `world-class`, `leverage`, `synergy`, `solutions`, `empower`.
- Passive voice in status, error, or confirmation messages.
- Third-person self-reference (`Symphony provides...`). Use `we`.
- Loading Poppins or any font from Google Fonts or another CDN.

## Source documents

- Brand book 2021 (visual identity, full detail): [`docs/brand-guidlines/Symphony-brandguidelines_2021.pdf`](../../../docs/brand-guidlines/Symphony-brandguidelines_2021.pdf)
- Voice and tone guide: [Google Doc](https://docs.google.com/document/d/1Jql49Vy7SeBaxdLwoR71fLe-4TIIBDbp6MMZlh4ymkA/edit)
- PRD design requirements: [`docs/prd.md`](../../../docs/prd.md) section 7.7
- Examples and side-by-side comparisons: [examples.md](examples.md)
