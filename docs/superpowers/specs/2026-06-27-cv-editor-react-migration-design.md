# CV Editor — React Migration & Enhanced Drafting

**Date:** 2026-06-27  
**Status:** Approved for implementation planning

## Context

The current draft editor (`dashboard/static/draft.html` + `draft.js`) is a standalone Vanilla JS page that lives outside the main React SPA. It handles CV and letter editing after Ollama generates a draft. Three limitations prompted this redesign:

1. **No block reordering** — experience roles and bullets cannot be moved up/down without cut-and-paste.
2. **No reprompt workflow** — once a draft is generated you can edit manually or start over with a new job application; there's no "try again with different instructions" action.
3. **No delete action** — removing a mistaken or rejected application requires going to the filesystem.

The editor is already form-driven (not YAML textarea), validates against Typst guard-rails in real time, and saves to the same YAML files on disk. This design migrates it into the React SPA and adds the three missing capabilities.

---

## Architecture

The `draft.html` and `draft.js` files are retired (kept on disk as a dead fallback). The main React SPA (`dashboard/web/src/`) gains a new `/draft/:folder` route. The Python server already serves `index.html` for all unmatched routes, so no server routing changes are needed.

New dependency: `@dnd-kit/core` + `@dnd-kit/sortable` — the standard drag-and-drop library for React. Lightweight, accessible, no peer conflicts with the existing Framer Motion / React 18 stack.

The existing `DraftContext` → `DraftOverlay` → navigate-to-`/draft?folder=...` flow remains identical; it now lands in the new React page.

---

## Components

All new files live under `dashboard/web/src/`:

```
pages/DraftPage.tsx                  ← route root; owns all editor state; loads GET /api/applications/{folder}/draft
components/draft/
  DraftHeader.tsx                    ← folder title, back button; Save / Build / Mark Ready / Reprompt / Delete
  DraftTabs.tsx                      ← CV | Letter | Listing | Preview tab switcher
  CVEditor.tsx                       ← tagline + profile fields; two SortableRoleLists (experience, additional)
  LetterEditor.tsx                   ← subtitle + SortableParagraphList
  SortableRoleList.tsx               ← dnd-kit DndContext + SortableContext for a list of role blocks
  SortableRoleBlock.tsx              ← drag handle + role/company/period/location inputs + SortableBulletList
  SortableBulletList.tsx             ← dnd-kit context for bullets within one role
  SortableBulletItem.tsx             ← textarea + char counter (≤165) + remove (×) button
  SortableParagraphItem.tsx          ← textarea + char counter for letter paragraphs; total-body counter shared
  RepromptModal.tsx                  ← mode toggle (fresh / refine) + instructions textarea + Generate button
  DeleteModal.tsx                    ← "Delete this application? Cannot be undone." + confirm/cancel
```

All character counter logic and field limits migrate directly from `draft.js` (same thresholds, same colour rules: yellow at 90%, red when exceeded). The existing typed API functions in `src/lib/api.ts` (`getDraft`, `saveDraft`, `buildApplication`, `setJobStatus`) stay unchanged. Two new typed functions are added: `repromptDraft`, `deleteDraft`. `markDraftReady` is a new wrapper around the existing `POST /api/applications/{folder}/ready-for-review` endpoint (the endpoint is unchanged).

---

## Drag-and-Drop

`@dnd-kit/sortable` wraps each list:

- **Experience roles** (two independent lists — `experience` and `additional`): each role card has a drag handle icon at the top-left. Dragging reorders within its list only (no moving between experience ↔ additional).
- **Bullets within a role**: each bullet row has its own drag handle. Dragging reorders within that role only.
- **Letter paragraphs**: same pattern.

On `onDragEnd`, the parent list state is updated with `arrayMove`. The state is dirty-flagged so the Save button activates. Keyboard navigation (arrow keys on the drag handle) is provided by dnd-kit by default.

---

## Reprompt UX

A **Reprompt** button in the header opens `RepromptModal`:

```
┌──────────────────────────────────────────────┐
│ Reprompt this draft                          │
│                                              │
│  Mode                                        │
│  ○ Fresh start                               │
│    Ignore current edits, generate a new      │
│    draft from the job listing.               │
│                                              │
│  ● Refine                                    │
│    Use my current edits as context; ask      │
│    Ollama to improve with these instructions.│
│                                              │
│  Instructions (optional)                     │
│  ┌─────────────────────────────────────────┐ │
│  │ e.g. Emphasize the LEGO retail          │ │
│  │ experience more...                      │ │
│  └─────────────────────────────────────────┘ │
│                    [Cancel]  [Generate →]    │
└──────────────────────────────────────────────┘
```

On confirm, the page **sends the current in-memory form state** as `current_draft` (for refine mode) — no auto-save before reprompting, so unsaved manual edits are included in the refinement context. For fresh mode, unsaved edits are discarded (the modal copy makes this explicit: "Ignore current edits"). The page then enters a loading state (same Angie thinking sprite used in `DraftOverlay`). On success, the form reloads with the new draft data. On error, an inline error message appears with a retry option.

---

## Delete UX

A **Delete** button in the header opens `DeleteModal` — a simple confirmation dialog: "Delete this application folder? This cannot be undone." On confirm, calls `DELETE /api/applications/{folder}`, then navigates back to the dashboard home.

---

## Backend Changes (`jobhunt/dashboard.py`)

### New: `POST /api/applications/{folder}/reprompt`

Request body:
```json
{
  "mode": "fresh" | "refine",
  "instructions": "string (may be empty)",
  "current_draft": { "cv": {...}, "letter": {...} }  // required for refine mode
}
```

- **`fresh`**: calls existing `generate_draft_with_ollama(row, listing, instructions)` — overwrites YAML files. Identical to the original draft-pack flow.
- **`refine`**: calls new `refine_draft_with_ollama(current_draft, listing, instructions)`. The prompt includes the current YAML as context with a new section prepended:

  ```
  CURRENT DRAFT (refine this, don't start from scratch):
  <current cv-data.yaml content>
  <current letter-data.yaml content>

  New instructions: <user instructions>
  ```

  Same JSON schema output, same `validate_draft_payload()`, same YAML write path. Updates `draft-meta.json` with `state: "draft_generated"`, `origin: "ollama"`, and the new `custom_instructions`.

Returns the same response shape as the existing draft-pack endpoint.

### New: `DELETE /api/applications/{folder}`

1. Removes `Applications/<folder>/` directory tree (`shutil.rmtree`).
2. Looks up the matching job row by `app_folder = folder` in SQLite; resets `status = 'reviewed'` and `app_folder = NULL`.
3. Returns HTTP 204.

No other backend changes. Save, build, mark-ready, and get-draft endpoints stay unchanged.

---

## Verification

1. `cd dashboard/web && npm run build` — must compile clean (no TypeScript errors).
2. `python -m jobhunt validate` — existing backend smoke test still passes.
3. Navigate to an existing application's draft URL → form loads with correct pre-filled data.
4. Drag an experience block up/down → Save → reload → confirm persisted order.
5. Drag a bullet within a role → confirm within-role order maintained, other roles unaffected.
6. Reprompt → Fresh mode → confirm new YAML overwrites, form reloads with fresh content.
7. Reprompt → Refine mode with instructions → confirm YAML updated and instructions visible in the generated text.
8. Delete → confirm folder removed from disk, job status reset to `reviewed`, navigates to dashboard.
9. Navigate to `/draft?folder=...` directly (old-style URL) → React page loads (not `draft.html`).
