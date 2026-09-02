# CV Editor — React Migration & Enhanced Drafting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Vanilla JS `draft.html`/`draft.js` editor into the React SPA, add drag-to-reorder blocks, and wire up reprompt (fresh + refine) and delete actions.

**Architecture:** The Python server is changed to serve `index.html` (the React SPA) for all `/draft` routes; `main.tsx` checks `window.location.pathname === '/draft'` and renders `<DraftPage />` instead of the main dashboard. Two new backend endpoints — `POST /api/applications/{folder}/reprompt` and `DELETE /api/applications/{folder}` — handle AI re-generation and folder cleanup. `@dnd-kit/sortable` provides drag-to-reorder for experience roles, bullets, and letter paragraphs.

**Tech Stack:** Python stdlib HTTP (dashboard.py), React 18 + TypeScript + Vite, `@dnd-kit/core` + `@dnd-kit/sortable`, existing app.css design tokens.

## Global Constraints

- Never edit files in `Base/` — the Typst templates are frozen.
- All YAML edits go through `PUT /api/applications/{folder}/draft` (the existing save endpoint, unchanged).
- Character limits: tagline ≤170, profile ≤600, bullet ≤165, letter body ≤2050 total chars.
- Keep `draft.html` and `draft.js` on disk (dead fallback) — do not delete them.
- `npm` commands run inside `dashboard/web/` (where `package.json` lives).
- Build output: `dashboard/static/app/` — run `npm run build` from `dashboard/web/` after frontend changes.
- Backend: `python -m jobhunt validate` must pass after each Python task.
- CSS tokens: use `var(--rose)`, `var(--ink)`, `var(--border)`, `var(--radius-sm)`, `var(--surface)`, `var(--font-body)`, `var(--font-display)` — defined in `src/styles/tokens.css`.
- Existing React CSS classes to reuse: `.btn`, `.btn.ghost`, `.btn.sm`, `.btn.rose`, `.field`, `.modal-backdrop`, `.panel`, `.panel-sub` (all in `src/styles/app.css`).

---

### Task 1: Backend — Reprompt endpoint

**Files:**
- Modify: `jobhunt/dashboard.py`

**Interfaces:**
- Produces: `POST /api/applications/{folder}/reprompt` → returns same shape as `GET /api/applications/{folder}/draft` (the `DraftDoc` dict from `read_application_draft()`)
- New functions: `_refine_prompt(current_yaml, listing, instructions) -> str`, `_refine_draft_with_ollama(current_draft_payload, listing, instructions) -> tuple[dict, dict, list[str]]`, `reprompt_draft(folder_name, mode, instructions, current_draft_payload, job_id, conn) -> dict`

- [ ] **Step 1: Add `shutil` import**

In `jobhunt/dashboard.py`, add to the stdlib import block (after `import sys`):

```python
import shutil
```

- [ ] **Step 2: Add `_refine_prompt` function**

After `_draft_prompt` (around line 631), add:

```python
def _refine_prompt(current_yaml: str, listing: str, instructions: str) -> str:
    guidance = instructions.strip()
    guidance_block = f"\nNEW INSTRUCTIONS:\n{guidance}\n" if guidance else ""
    return f"""
You are refining Angelica Barasoain's CV and motivation letter draft.
Return STRICT JSON only. No markdown, no explanation.

JSON schema (same structure as input):
{{
  "cv": {{
    "max_pages": 2,
    "title": "short role-target line",
    "tagline": "one sentence <=170 chars",
    "profile": "summary paragraph <=600 chars",
    "experience": [{{"role": "...", "company": "...", "period": "...", "location": "...", "bullets": ["<=165 chars each"]}}],
    "additional": [{{"role": "...", "company": "...", "period": "...", "location": "...", "bullets": ["<=165 chars each"]}}]
  }},
  "letter": {{
    "max_pages": 1,
    "subtitle": "...",
    "paragraphs": ["3 to 5 concise paragraphs, total <=2050 chars"]
  }}
}}

Rules:
- Use only facts present in the CURRENT DRAFT below. Do not invent new employers, tools, metrics, or claims.
- Improve prose, tighten bullets to <=165 chars, apply the new instructions.
- Return valid JSON that is an improvement on the current draft.
{guidance_block}

CURRENT DRAFT (refine this):
{current_yaml}

JOB LISTING (context):
{listing[:4000]}

CANDIDATE FACTS (reference only — do not add new ones):
{ANGELICA_FACTS}
""".strip()
```

- [ ] **Step 3: Add `_refine_draft_with_ollama` function**

After `_refine_prompt`, add:

```python
def _refine_draft_with_ollama(
    current_draft_payload: dict, listing: str, instructions: str
) -> tuple[dict, dict, list[str]]:
    cv_data, letter_data, _ = validate_draft_payload(current_draft_payload)
    current_yaml = (
        "CV:\n"
        + yaml.safe_dump(cv_data, sort_keys=False, allow_unicode=True, width=110)
        + "\nLETTER:\n"
        + yaml.safe_dump(letter_data, sort_keys=False, allow_unicode=True, width=110)
    )
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": _refine_prompt(current_yaml, listing, instructions),
        "stream": False,
        "options": {"temperature": 0.25, "num_ctx": 12000},
    }
    request = Request(
        f"{OLLAMA_URL.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=240) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Ollama refinement failed: {exc}") from exc
    raw = data.get("response")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Ollama returned an empty response.")
    return validate_draft_payload(_extract_json_object(raw))
```

- [ ] **Step 4: Add `reprompt_draft` function**

After `_refine_draft_with_ollama`, add:

```python
def reprompt_draft(
    folder_name: str,
    mode: str,
    instructions: str,
    current_draft_payload: dict,
    job_id: int | None,
    conn: sqlite3.Connection,
) -> dict:
    if mode not in ("fresh", "refine"):
        raise ValueError("mode must be 'fresh' or 'refine'.")
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    listing = (folder / "job-listing.md").read_text(encoding="utf-8") if (folder / "job-listing.md").exists() else ""

    if mode == "fresh":
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone() if job_id else None
        if not row:
            raise ValueError("job_id is required for fresh mode (could not find job row).")
        cv_data, letter_data, warnings = generate_draft_with_ollama(row, listing, instructions)
    else:
        cv_data, letter_data, warnings = _refine_draft_with_ollama(current_draft_payload, listing, instructions)

    _write_yaml(folder / "cv-data.yaml", cv_data, f"# Draft CV for: {folder_name}")
    _write_yaml(folder / "letter-data.yaml", letter_data, f"# Draft motivation letter for: {folder_name}")
    write_draft_meta(
        folder,
        {
            "origin": "ollama",
            "model": OLLAMA_MODEL,
            "state": "draft_generated",
            "updated_at": _now_iso(),
            "custom_instructions": instructions.strip(),
        },
    )
    return read_application_draft(folder.name) | {"warnings": warnings}
```

- [ ] **Step 5: Register the route in `do_POST`**

In `do_POST`, after the `ready_match` block (around line 1152) and before the final `"Not found"` return, add:

```python
reprompt_match = re.match(r"^/api/applications/([^/]+)/reprompt$", parsed.path)
if reprompt_match:
    mode = str(payload.get("mode") or "fresh")
    instructions = str(payload.get("instructions") or "")
    current_draft = payload.get("current_draft") or {}
    job_id_val = payload.get("job_id")
    job_id = int(job_id_val) if job_id_val else None
    with init_db(connect(DB_PATH)) as conn:
        self._send_json(reprompt_draft(reprompt_match.group(1), mode, instructions, current_draft, job_id, conn))
    return
```

- [ ] **Step 6: Verify backend**

```bash
cd /opt/angelica-jobhunt && python -m jobhunt validate
```

Expected: `OK` or no import errors related to dashboard.py.

- [ ] **Step 7: Commit**

```bash
cd /opt/angelica-jobhunt
git add jobhunt/dashboard.py
git commit -m "feat(backend): add reprompt endpoint with fresh + refine modes"
```

---

### Task 2: Backend — Delete endpoint + fix /draft routing

**Files:**
- Modify: `jobhunt/dashboard.py`

**Interfaces:**
- Produces: `DELETE /api/applications/{folder}?job_id=123` → HTTP 204, no body
- New function: `delete_application(folder_name, job_id, conn) -> None`
- Routing change: `/draft` → serves `index.html` instead of `draft.html`

- [ ] **Step 1: Add `delete_application` function**

After `reprompt_draft` (just added in Task 1), add:

```python
def delete_application(folder_name: str, job_id: int | None, conn: sqlite3.Connection) -> None:
    folder = _safe_application_dir(folder_name)
    if not folder.is_dir():
        raise ValueError(f"Application folder not found: {folder_name}")
    if job_id is not None:
        conn.execute(
            "UPDATE jobs SET status = 'reviewed' WHERE id = ? AND status IN ('tailoring', 'ready', 'draft_generated')",
            (job_id,),
        )
        conn.commit()
    shutil.rmtree(folder)
```

- [ ] **Step 2: Add `do_DELETE` method to `DashboardHandler`**

After `do_PUT` (around line 1184), add a new method to `DashboardHandler`:

```python
def do_DELETE(self) -> None:  # noqa: N802
    parsed = urlparse(self.path)
    try:
        app_match = re.match(r"^/api/applications/([^/]+)$", parsed.path)
        if app_match:
            qs = parse_qs(parsed.query)
            job_id_str = (qs.get("job_id") or [None])[0]
            job_id = int(job_id_str) if job_id_str and job_id_str.isdigit() else None
            with init_db(connect(DB_PATH)) as conn:
                delete_application(app_match.group(1), job_id, conn)
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self._send_error_json("Not found", HTTPStatus.NOT_FOUND)
    except ValueError as exc:
        self._send_error_json(str(exc), HTTPStatus.BAD_REQUEST)
    except Exception as exc:  # pragma: no cover
        self.log_message("unhandled DELETE error: %s", exc)
        self._send_error_json("Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR)
```

- [ ] **Step 3: Fix /draft routing**

In `_serve_static`, change line 1189-1190 from:

```python
elif request_path in ("/draft", "/draft/") or request_path.startswith("/draft/"):
    path = "draft.html"
```

to:

```python
elif request_path in ("/draft", "/draft/") or request_path.startswith("/draft/"):
    path = "index.html"
```

This makes `/draft` serve the React SPA (`index.html`), which will then render `DraftPage` (added in Task 10).

- [ ] **Step 4: Verify backend**

```bash
cd /opt/angelica-jobhunt && python -m jobhunt validate
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd /opt/angelica-jobhunt
git add jobhunt/dashboard.py
git commit -m "feat(backend): add delete endpoint, fix /draft routing to serve React SPA"
```

---

### Task 3: Frontend — Install dnd-kit and add API types/functions

**Files:**
- Modify: `dashboard/web/package.json` (via npm)
- Modify: `dashboard/web/src/lib/api.ts`

**Interfaces:**
- Produces types: `Role`, `CvData`, `LetterData`, `DraftLimits`, `DraftDoc`
- Produces functions: `getDraft(folder)`, `saveDraft(folder, payload)`, `buildApplication(folder)`, `markDraftReady(folder, jobId?)`, `repromptDraft(folder, body)`, `deleteDraft(folder, jobId?)`

- [ ] **Step 1: Install dnd-kit**

```bash
cd /opt/angelica-jobhunt/dashboard/web
npm install @dnd-kit/core @dnd-kit/sortable
```

Expected: packages added to `package.json` dependencies; `node_modules/@dnd-kit/` exists.

- [ ] **Step 2: Add types to `api.ts`**

At the top of `dashboard/web/src/lib/api.ts`, after the existing type exports, add:

```typescript
export type Role = {
  role: string;
  company: string;
  period: string;
  location: string;
  bullets: string[];
};

export type CvData = {
  max_pages: number;
  title: string;
  tagline: string;
  profile: string;
  experience: Role[];
  additional: Role[];
};

export type LetterData = {
  max_pages: number;
  subtitle: string;
  paragraphs: string[];
};

export type DraftLimits = {
  tagline: number;
  profile: number;
  bullet: number;
  letter_body: number;
};

export type DraftDoc = {
  folder_name: string;
  cv: CvData;
  letter: LetterData;
  listing: string;
  artifact: Artifact;
  warnings: string[];
  limits: DraftLimits;
  meta: Record<string, unknown>;
};

export type RepromptBody = {
  mode: "fresh" | "refine";
  instructions: string;
  job_id?: number;
  current_draft?: { cv: CvData; letter: LetterData };
};
```

- [ ] **Step 3: Add API functions to `api.ts`**

At the bottom of `dashboard/web/src/lib/api.ts`, add:

```typescript
export const getDraft = (folder: string) =>
  api<DraftDoc>(`/api/applications/${encodeURIComponent(folder)}/draft`);

export const saveDraft = (folder: string, payload: { cv: CvData; letter: LetterData }) =>
  api<DraftDoc>(`/api/applications/${encodeURIComponent(folder)}/draft`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });

export const buildApplication = (folder: string) =>
  api<{ ok: boolean; folder_name: string; artifact: Artifact; output: string; error: string | null }>(
    `/api/applications/${encodeURIComponent(folder)}/build`,
    { method: "POST", body: JSON.stringify({}) }
  );

export const markDraftReady = (folder: string, jobId?: number) =>
  api<DraftDoc>(`/api/applications/${encodeURIComponent(folder)}/ready-for-review`, {
    method: "POST",
    body: JSON.stringify(jobId ? { job_id: jobId } : {}),
  });

export const repromptDraft = (folder: string, body: RepromptBody) =>
  api<DraftDoc>(`/api/applications/${encodeURIComponent(folder)}/reprompt`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const deleteDraft = async (folder: string, jobId?: number): Promise<void> => {
  const qs = jobId ? `?job_id=${jobId}` : "";
  const res = await fetch(`/api/applications/${encodeURIComponent(folder)}${qs}`, {
    method: "DELETE",
  });
  if (res.status === 204) return;
  const payload = await res.json().catch(() => ({}));
  throw new Error((payload as { error?: string }).error || `Delete failed: ${res.status}`);
};
```

- [ ] **Step 4: TypeScript check**

```bash
cd /opt/angelica-jobhunt/dashboard/web && npm run build 2>&1 | head -30
```

Expected: build succeeds (or fails only on unrelated existing issues — no new TS errors from api.ts).

- [ ] **Step 5: Commit**

```bash
cd /opt/angelica-jobhunt
git add dashboard/web/package.json dashboard/web/package-lock.json dashboard/web/src/lib/api.ts
git commit -m "feat(frontend): install dnd-kit, add draft API types and functions"
```

---

### Task 4: Sortable bullet and paragraph components

**Files:**
- Create: `dashboard/web/src/components/draft/SortableBulletItem.tsx`
- Create: `dashboard/web/src/components/draft/SortableBulletList.tsx`
- Create: `dashboard/web/src/components/draft/SortableParagraphItem.tsx`

**Interfaces:**
- `SortableBulletItem` props: `{ id: string; text: string; onChange: (text: string) => void; onRemove: () => void; limit: number }`
- `SortableBulletList` props: `{ bullets: Array<{ id: string; text: string }>; limit: number; onChange: (bullets: Array<{ id: string; text: string }>) => void }`
- `SortableParagraphItem` props: `{ id: string; text: string; index: number; onChange: (text: string) => void }`

- [ ] **Step 1: Write `SortableBulletItem.tsx`**

```tsx
// dashboard/web/src/components/draft/SortableBulletItem.tsx
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

type Props = {
  id: string;
  text: string;
  limit: number;
  onChange: (text: string) => void;
  onRemove: () => void;
};

function charClass(len: number, limit: number) {
  if (len > limit) return "counter-error";
  if (len > Math.floor(limit * 0.9)) return "counter-warn";
  return "";
}

export function SortableBulletItem({ id, text, limit, onChange, onRemove }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  const len = text.length;
  return (
    <div ref={setNodeRef} style={style} className="draft-bullet-row">
      <button
        type="button"
        className="drag-handle"
        aria-label="Drag to reorder bullet"
        {...attributes}
        {...listeners}
      >
        ⠿
      </button>
      <div className="draft-bullet-body">
        <textarea
          rows={2}
          value={text}
          onChange={(e) => onChange(e.target.value)}
          className="draft-bullet-textarea"
        />
        <span className={`field-counter ${charClass(len, limit)}`}>
          {len} / {limit}
        </span>
      </div>
      <button type="button" className="draft-remove" onClick={onRemove} aria-label="Remove bullet">
        ×
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Write `SortableBulletList.tsx`**

```tsx
// dashboard/web/src/components/draft/SortableBulletList.tsx
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { SortableBulletItem } from "./SortableBulletItem";

type Bullet = { id: string; text: string };

type Props = {
  bullets: Bullet[];
  limit: number;
  onChange: (bullets: Bullet[]) => void;
};

export function SortableBulletList({ bullets, limit, onChange }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = bullets.findIndex((b) => b.id === active.id);
      const newIndex = bullets.findIndex((b) => b.id === over.id);
      onChange(arrayMove(bullets, oldIndex, newIndex));
    }
  }

  function updateBullet(id: string, text: string) {
    onChange(bullets.map((b) => (b.id === id ? { ...b, text } : b)));
  }

  function removeBullet(id: string) {
    onChange(bullets.filter((b) => b.id !== id));
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={bullets.map((b) => b.id)} strategy={verticalListSortingStrategy}>
        {bullets.map((b) => (
          <SortableBulletItem
            key={b.id}
            id={b.id}
            text={b.text}
            limit={limit}
            onChange={(text) => updateBullet(b.id, text)}
            onRemove={() => removeBullet(b.id)}
          />
        ))}
      </SortableContext>
    </DndContext>
  );
}
```

- [ ] **Step 3: Write `SortableParagraphItem.tsx`**

```tsx
// dashboard/web/src/components/draft/SortableParagraphItem.tsx
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

type Props = {
  id: string;
  text: string;
  index: number;
  onChange: (text: string) => void;
};

export function SortableParagraphItem({ id, text, index, onChange }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  return (
    <div ref={setNodeRef} style={style} className="draft-para-row">
      <button
        type="button"
        className="drag-handle"
        aria-label={`Drag paragraph ${index + 1}`}
        {...attributes}
        {...listeners}
      >
        ⠿
      </button>
      <label className="field" style={{ flex: 1 }}>
        Paragraph {index + 1}
        <textarea rows={5} value={text} onChange={(e) => onChange(e.target.value)} />
      </label>
    </div>
  );
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd /opt/angelica-jobhunt/dashboard/web && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors from the three new files.

- [ ] **Step 5: Commit**

```bash
cd /opt/angelica-jobhunt
git add dashboard/web/src/components/draft/
git commit -m "feat(frontend): add sortable bullet and paragraph components"
```

---

### Task 5: Sortable role components

**Files:**
- Create: `dashboard/web/src/components/draft/SortableRoleBlock.tsx`
- Create: `dashboard/web/src/components/draft/SortableRoleList.tsx`

**Interfaces:**
- Consumed types: `SortableBulletList`, `SortableBulletItem` from Task 4
- `SortableRole`: `{ id: string; role: string; company: string; period: string; location: string; bullets: Array<{ id: string; text: string }> }`
- `SortableRoleBlock` props: `{ id: string; roleData: SortableRole; bulletLimit: number; onChange: (role: SortableRole) => void; onRemove: () => void }`
- `SortableRoleList` props: `{ roles: SortableRole[]; bulletLimit: number; onChange: (roles: SortableRole[]) => void }`
- Export: `SortableRole` type (re-used in Task 6, 7, 10)

- [ ] **Step 1: Write `SortableRoleBlock.tsx`**

```tsx
// dashboard/web/src/components/draft/SortableRoleBlock.tsx
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { SortableBulletList } from "./SortableBulletList";

export type SortableRole = {
  id: string;
  role: string;
  company: string;
  period: string;
  location: string;
  bullets: Array<{ id: string; text: string }>;
};

type Props = {
  id: string;
  roleData: SortableRole;
  bulletLimit: number;
  onChange: (role: SortableRole) => void;
  onRemove: () => void;
};

export function SortableRoleBlock({ id, roleData, bulletLimit, onChange, onRemove }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  function field(key: keyof Omit<SortableRole, "id" | "bullets">) {
    return (
      <label className="field">
        {key.charAt(0).toUpperCase() + key.slice(1)}
        <input
          type="text"
          value={roleData[key]}
          onChange={(e) => onChange({ ...roleData, [key]: e.target.value })}
        />
      </label>
    );
  }

  function addBullet() {
    if (roleData.bullets.length >= 5) return;
    onChange({
      ...roleData,
      bullets: [...roleData.bullets, { id: crypto.randomUUID(), text: "" }],
    });
  }

  return (
    <div ref={setNodeRef} style={style} className="draft-role-card">
      <div className="draft-role-card-header">
        <button
          type="button"
          className="drag-handle role-drag"
          aria-label="Drag to reorder role"
          {...attributes}
          {...listeners}
        >
          ⠿
        </button>
        <span className="draft-role-label">
          {roleData.role || "Untitled role"} · {roleData.company || "—"}
        </span>
        <button type="button" className="draft-remove" onClick={onRemove} aria-label="Remove role">
          ×
        </button>
      </div>
      <div className="draft-role-grid">
        {field("role")}
        {field("company")}
        {field("period")}
        {field("location")}
      </div>
      <SortableBulletList
        bullets={roleData.bullets}
        limit={bulletLimit}
        onChange={(bullets) => onChange({ ...roleData, bullets })}
      />
      {roleData.bullets.length < 5 && (
        <button type="button" className="btn ghost sm draft-add-bullet" onClick={addBullet}>
          + Add bullet
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write `SortableRoleList.tsx`**

```tsx
// dashboard/web/src/components/draft/SortableRoleList.tsx
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { SortableRoleBlock, type SortableRole } from "./SortableRoleBlock";

type Props = {
  roles: SortableRole[];
  bulletLimit: number;
  onChange: (roles: SortableRole[]) => void;
};

export function SortableRoleList({ roles, bulletLimit, onChange }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = roles.findIndex((r) => r.id === active.id);
      const newIndex = roles.findIndex((r) => r.id === over.id);
      onChange(arrayMove(roles, oldIndex, newIndex));
    }
  }

  function updateRole(id: string, updated: SortableRole) {
    onChange(roles.map((r) => (r.id === id ? updated : r)));
  }

  function removeRole(id: string) {
    onChange(roles.filter((r) => r.id !== id));
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={roles.map((r) => r.id)} strategy={verticalListSortingStrategy}>
        {roles.map((r) => (
          <SortableRoleBlock
            key={r.id}
            id={r.id}
            roleData={r}
            bulletLimit={bulletLimit}
            onChange={(updated) => updateRole(r.id, updated)}
            onRemove={() => removeRole(r.id)}
          />
        ))}
      </SortableContext>
    </DndContext>
  );
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /opt/angelica-jobhunt/dashboard/web && npx tsc --noEmit 2>&1 | head -30
```

Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/angelica-jobhunt
git add dashboard/web/src/components/draft/
git commit -m "feat(frontend): add sortable role block and role list components"
```

---

### Task 6: CV and Letter editor components

**Files:**
- Create: `dashboard/web/src/components/draft/CVEditor.tsx`
- Create: `dashboard/web/src/components/draft/LetterEditor.tsx`

**Interfaces:**
- Consumed: `SortableRoleList`, `SortableRole` (Task 5), `SortableParagraphItem` (Task 4)
- `CvState`: `{ title: string; tagline: string; profile: string; experience: SortableRole[]; additional: SortableRole[] }`
- `LetterState`: `{ subtitle: string; paragraphs: Array<{ id: string; text: string }> }`
- `CVEditor` props: `{ cv: CvState; limits: DraftLimits; onChange: (cv: CvState) => void }`
- `LetterEditor` props: `{ letter: LetterState; limits: DraftLimits; onChange: (letter: LetterState) => void }`
- Export: `CvState`, `LetterState` types (re-used in Tasks 7, 8, 10)

- [ ] **Step 1: Write `CVEditor.tsx`**

```tsx
// dashboard/web/src/components/draft/CVEditor.tsx
import type { DraftLimits } from "../../lib/api";
import { SortableRoleList, type SortableRole } from "./SortableRoleList";

export type CvState = {
  title: string;
  tagline: string;
  profile: string;
  experience: SortableRole[];
  additional: SortableRole[];
};

function charClass(len: number, limit: number) {
  if (len > limit) return "counter-error";
  if (len > Math.floor(limit * 0.9)) return "counter-warn";
  return "";
}

function addBlankRole(list: SortableRole[]): SortableRole[] {
  return [
    ...list,
    { id: crypto.randomUUID(), role: "", company: "", period: "", location: "", bullets: [] },
  ];
}

type Props = { cv: CvState; limits: DraftLimits; onChange: (cv: CvState) => void };

export function CVEditor({ cv, limits, onChange }: Props) {
  const tagLen = cv.tagline.length;
  const profLen = cv.profile.length;

  return (
    <div className="draft-editor">
      <label className="field">
        Target title
        <input
          type="text"
          value={cv.title}
          onChange={(e) => onChange({ ...cv, title: e.target.value })}
        />
      </label>

      <label className="field">
        Tagline
        <textarea
          rows={3}
          value={cv.tagline}
          onChange={(e) => onChange({ ...cv, tagline: e.target.value })}
        />
        <span className={`field-counter ${charClass(tagLen, limits.tagline)}`}>
          {tagLen} / {limits.tagline}
        </span>
      </label>

      <label className="field">
        Profile
        <textarea
          rows={5}
          value={cv.profile}
          onChange={(e) => onChange({ ...cv, profile: e.target.value })}
        />
        <span className={`field-counter ${charClass(profLen, limits.profile)}`}>
          {profLen} / {limits.profile}
        </span>
      </label>

      <div className="draft-section-header">
        <h3>Experience</h3>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => onChange({ ...cv, experience: addBlankRole(cv.experience) })}
        >
          + Add role
        </button>
      </div>
      <SortableRoleList
        roles={cv.experience}
        bulletLimit={limits.bullet}
        onChange={(experience) => onChange({ ...cv, experience })}
      />

      <div className="draft-section-header">
        <h3>Additional Experience</h3>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => onChange({ ...cv, additional: addBlankRole(cv.additional) })}
        >
          + Add role
        </button>
      </div>
      <SortableRoleList
        roles={cv.additional}
        bulletLimit={limits.bullet}
        onChange={(additional) => onChange({ ...cv, additional })}
      />
    </div>
  );
}
```

- [ ] **Step 2: Write `LetterEditor.tsx`**

```tsx
// dashboard/web/src/components/draft/LetterEditor.tsx
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import type { DraftLimits } from "../../lib/api";
import { SortableParagraphItem } from "./SortableParagraphItem";

export type LetterState = {
  subtitle: string;
  paragraphs: Array<{ id: string; text: string }>;
};

function charClass(len: number, limit: number) {
  if (len > limit) return "counter-error";
  if (len > Math.floor(limit * 0.9)) return "counter-warn";
  return "";
}

type Props = { letter: LetterState; limits: DraftLimits; onChange: (letter: LetterState) => void };

export function LetterEditor({ letter, limits, onChange }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const bodyLen = letter.paragraphs.reduce((s, p) => s + p.text.length, 0);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = letter.paragraphs.findIndex((p) => p.id === active.id);
      const newIndex = letter.paragraphs.findIndex((p) => p.id === over.id);
      onChange({ ...letter, paragraphs: arrayMove(letter.paragraphs, oldIndex, newIndex) });
    }
  }

  function updatePara(id: string, text: string) {
    onChange({
      ...letter,
      paragraphs: letter.paragraphs.map((p) => (p.id === id ? { ...p, text } : p)),
    });
  }

  function addParagraph() {
    if (letter.paragraphs.length >= 5) return;
    onChange({
      ...letter,
      paragraphs: [...letter.paragraphs, { id: crypto.randomUUID(), text: "" }],
    });
  }

  function removeParagraph(id: string) {
    onChange({ ...letter, paragraphs: letter.paragraphs.filter((p) => p.id !== id) });
  }

  return (
    <div className="draft-editor">
      <label className="field">
        Subtitle
        <input
          type="text"
          value={letter.subtitle}
          onChange={(e) => onChange({ ...letter, subtitle: e.target.value })}
        />
      </label>

      <div className="draft-limit-row">
        <span>{letter.paragraphs.length} paragraph{letter.paragraphs.length !== 1 ? "s" : ""}</span>
        <span className={`field-counter ${charClass(bodyLen, limits.letter_body)}`}>
          {bodyLen} / {limits.letter_body} total chars
        </span>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext
          items={letter.paragraphs.map((p) => p.id)}
          strategy={verticalListSortingStrategy}
        >
          {letter.paragraphs.map((p, i) => (
            <div key={p.id} className="draft-para-wrapper">
              <SortableParagraphItem id={p.id} text={p.text} index={i} onChange={(text) => updatePara(p.id, text)} />
              <button
                type="button"
                className="draft-remove para-remove"
                onClick={() => removeParagraph(p.id)}
                aria-label={`Remove paragraph ${i + 1}`}
              >
                ×
              </button>
            </div>
          ))}
        </SortableContext>
      </DndContext>

      {letter.paragraphs.length < 5 && (
        <button type="button" className="btn ghost sm" onClick={addParagraph}>
          + Add paragraph
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /opt/angelica-jobhunt/dashboard/web && npx tsc --noEmit 2>&1 | head -30
```

Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/angelica-jobhunt
git add dashboard/web/src/components/draft/
git commit -m "feat(frontend): add CVEditor and LetterEditor components"
```

---

### Task 7: Reprompt and Delete modals

**Files:**
- Create: `dashboard/web/src/components/draft/RepromptModal.tsx`
- Create: `dashboard/web/src/components/draft/DeleteModal.tsx`

**Interfaces:**
- Consumed: `CvState`, `LetterState` (Task 6), `RepromptBody` type from `api.ts`
- `RepromptModal` props: `{ folder: string; jobId?: number; currentCv: CvState; currentLetter: LetterState; onSuccess: (doc: DraftDoc) => void; onClose: () => void }`
- `DeleteModal` props: `{ folder: string; jobId?: number; onSuccess: () => void; onClose: () => void }`

- [ ] **Step 1: Write `RepromptModal.tsx`**

```tsx
// dashboard/web/src/components/draft/RepromptModal.tsx
import { useState } from "react";
import { Angie } from "../Sprite";
import { repromptDraft, type DraftDoc, type CvData, type LetterData } from "../../lib/api";
import type { CvState } from "./CVEditor";
import type { LetterState } from "./LetterEditor";

type Props = {
  folder: string;
  jobId?: number;
  currentCv: CvState;
  currentLetter: LetterState;
  onSuccess: (doc: DraftDoc) => void;
  onClose: () => void;
};

function cvStateToPayload(cv: CvState): CvData {
  return {
    max_pages: 2,
    title: cv.title,
    tagline: cv.tagline,
    profile: cv.profile,
    experience: cv.experience.map((r) => ({
      role: r.role, company: r.company, period: r.period, location: r.location,
      bullets: r.bullets.map((b) => b.text).filter(Boolean),
    })),
    additional: cv.additional.map((r) => ({
      role: r.role, company: r.company, period: r.period, location: r.location,
      bullets: r.bullets.map((b) => b.text).filter(Boolean),
    })),
  };
}

function letterStateToPayload(letter: LetterState): LetterData {
  return {
    max_pages: 1,
    subtitle: letter.subtitle,
    paragraphs: letter.paragraphs.map((p) => p.text).filter(Boolean),
  };
}

export function RepromptModal({ folder, jobId, currentCv, currentLetter, onSuccess, onClose }: Props) {
  const [mode, setMode] = useState<"fresh" | "refine">("refine");
  const [instructions, setInstructions] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const body =
        mode === "fresh"
          ? { mode: "fresh" as const, instructions, job_id: jobId }
          : {
              mode: "refine" as const,
              instructions,
              current_draft: { cv: cvStateToPayload(currentCv), letter: letterStateToPayload(currentLetter) },
            };
      const doc = await repromptDraft(folder, body);
      onSuccess(doc);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGenerating(false);
    }
  }

  if (generating) {
    return (
      <div className="modal-backdrop is-busy" role="status" aria-live="polite">
        <section className="draft-loading-card">
          <Angie size="md" state="work" />
          <div>
            <h2>Reprompting draft</h2>
            <p>{mode === "fresh" ? "Generating fresh draft…" : "Refining current draft…"}</p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section
        className="draft-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reprompt-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="reprompt-title">Reprompt this draft</h2>

        <fieldset className="reprompt-modes">
          <legend className="field-label">Mode</legend>
          {(["fresh", "refine"] as const).map((m) => (
            <label key={m} className="reprompt-mode-option">
              <input type="radio" name="reprompt-mode" value={m} checked={mode === m} onChange={() => setMode(m)} />
              <div>
                <strong>{m === "fresh" ? "Fresh start" : "Refine"}</strong>
                <p className="panel-sub">
                  {m === "fresh"
                    ? "Ignore current edits — generate a new draft from the job listing."
                    : "Use my current edits as context; ask Ollama to improve with these instructions."}
                </p>
              </div>
            </label>
          ))}
        </fieldset>

        <label className="field">
          Instructions (optional)
          <textarea
            rows={4}
            placeholder="e.g. Emphasize the LEGO retail experience more prominently"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </label>

        {error && <p className="draft-error">{error}</p>}

        <div className="draft-modal-actions">
          <button type="button" className="btn ghost sm" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn rose sm" onClick={handleGenerate}>
            Generate →
          </button>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Write `DeleteModal.tsx`**

```tsx
// dashboard/web/src/components/draft/DeleteModal.tsx
import { useState } from "react";
import { deleteDraft } from "../../lib/api";

type Props = {
  folder: string;
  jobId?: number;
  onSuccess: () => void;
  onClose: () => void;
};

export function DeleteModal({ folder, jobId, onSuccess, onClose }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleDelete() {
    setBusy(true);
    setError("");
    try {
      await deleteDraft(folder, jobId);
      onSuccess();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={!busy ? onClose : undefined}>
      <section
        className="draft-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="delete-title">Delete this application?</h2>
        <p className="panel-sub">
          This will permanently remove the <strong>{folder}</strong> folder and all its files. This
          cannot be undone.
        </p>
        {error && <p className="draft-error">{error}</p>}
        <div className="draft-modal-actions">
          <button type="button" className="btn ghost sm" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="btn rose sm" onClick={handleDelete} disabled={busy}>
            {busy ? "Deleting…" : "Delete"}
          </button>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /opt/angelica-jobhunt/dashboard/web && npx tsc --noEmit 2>&1 | head -30
```

Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/angelica-jobhunt
git add dashboard/web/src/components/draft/
git commit -m "feat(frontend): add RepromptModal and DeleteModal components"
```

---

### Task 8: DraftHeader and DraftTabs components

**Files:**
- Create: `dashboard/web/src/components/draft/DraftHeader.tsx`
- Create: `dashboard/web/src/components/draft/DraftTabs.tsx`

**Interfaces:**
- `TabKey`: `"cv" | "letter" | "listing" | "preview"`
- `DraftHeader` props: `{ folder: string; dirty: boolean; busy: boolean; onSave: () => void; onBuild: () => void; onMarkReady: () => void; onReprompt: () => void; onDelete: () => void }`
- `DraftTabs` props: `{ active: TabKey; onChange: (tab: TabKey) => void }`

- [ ] **Step 1: Write `DraftHeader.tsx`**

```tsx
// dashboard/web/src/components/draft/DraftHeader.tsx

type Props = {
  folder: string;
  dirty: boolean;
  busy: boolean;
  onSave: () => void;
  onBuild: () => void;
  onMarkReady: () => void;
  onReprompt: () => void;
  onDelete: () => void;
};

export function DraftHeader({ folder, dirty, busy, onSave, onBuild, onMarkReady, onReprompt, onDelete }: Props) {
  return (
    <header className="draft-topbar">
      <div className="draft-topbar-info">
        <p className="draft-kicker">Angelica Job Hunt HQ</p>
        <h1 className="draft-topbar-title">{folder}</h1>
      </div>
      <div className="draft-topbar-actions">
        <a className="btn ghost sm" href="/">
          ← Dashboard
        </a>
        <button type="button" className="btn ghost sm" onClick={onReprompt} disabled={busy}>
          Reprompt
        </button>
        <button type="button" className="btn ghost sm" onClick={onMarkReady} disabled={busy}>
          Mark Ready
        </button>
        <button type="button" className="btn ghost sm" onClick={onBuild} disabled={busy}>
          Build PDF
        </button>
        <button
          type="button"
          className={`btn sm ${dirty ? "rose" : "ghost"}`}
          onClick={onSave}
          disabled={busy || !dirty}
        >
          {dirty ? "Save *" : "Saved"}
        </button>
        <button type="button" className="btn ghost sm draft-delete-btn" onClick={onDelete} disabled={busy}>
          Delete
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Write `DraftTabs.tsx`**

```tsx
// dashboard/web/src/components/draft/DraftTabs.tsx

export type TabKey = "cv" | "letter" | "listing" | "preview";

const TABS: { key: TabKey; label: string }[] = [
  { key: "cv", label: "CV" },
  { key: "letter", label: "Letter" },
  { key: "listing", label: "Listing" },
  { key: "preview", label: "Preview" },
];

type Props = { active: TabKey; onChange: (tab: TabKey) => void };

export function DraftTabs({ active, onChange }: Props) {
  return (
    <div className="draft-tabs" role="tablist">
      {TABS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          role="tab"
          aria-selected={active === key}
          className={active === key ? "active" : ""}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /opt/angelica-jobhunt/dashboard/web && npx tsc --noEmit 2>&1 | head -30
```

Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/angelica-jobhunt
git add dashboard/web/src/components/draft/
git commit -m "feat(frontend): add DraftHeader and DraftTabs components"
```

---

### Task 9: Draft CSS

**Files:**
- Create: `dashboard/web/src/styles/draft.css`

**Interfaces:**
- Produces CSS classes: `.draft-page`, `.draft-topbar`, `.draft-topbar-info`, `.draft-topbar-actions`, `.draft-topbar-title`, `.draft-kicker`, `.draft-tabs`, `.draft-tabs button`, `.draft-tabs button.active`, `.draft-editor`, `.draft-section-header`, `.draft-role-card`, `.draft-role-card-header`, `.draft-role-label`, `.draft-role-grid`, `.draft-bullet-row`, `.draft-bullet-body`, `.draft-bullet-textarea`, `.draft-para-row`, `.draft-para-wrapper`, `.draft-limit-row`, `.draft-warnings`, `.draft-status-msg`, `.draft-error`, `.drag-handle`, `.draft-remove`, `.draft-delete-btn`, `.draft-modal`, `.draft-modal-actions`, `.reprompt-modes`, `.reprompt-mode-option`, `.draft-add-bullet`, `.field-counter`, `.counter-warn`, `.counter-error`, `.preview-grid`, `.listing-preview`
- Imported by: `DraftPage.tsx` (Task 10)

- [ ] **Step 1: Write `draft.css`**

```css
/* dashboard/web/src/styles/draft.css */
/* Draft editor page — imported by DraftPage.tsx */

.draft-page {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}

/* ── Header ── */
.draft-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.draft-kicker {
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-faint);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0;
}
.draft-topbar-title {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  margin: 2px 0 0;
  color: var(--ink);
}
.draft-topbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.draft-delete-btn { color: var(--rose-deep) !important; }

/* ── Main canvas ── */
.draft-canvas {
  flex: 1;
  max-width: 860px;
  width: 100%;
  margin: 0 auto;
  padding: 28px 24px 60px;
}

/* ── Status message ── */
.draft-status-msg {
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1px solid var(--border);
  font-size: 13px;
  color: var(--ink-soft);
  margin-bottom: 16px;
}
.draft-error {
  color: var(--rose-deep);
  font-size: 13px;
  font-weight: 600;
  margin: 8px 0;
}
.draft-warnings {
  background: var(--butter-soft);
  border: 1px solid var(--butter);
  border-radius: var(--radius-sm);
  padding: 10px 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--butter-deep);
  list-style: disc;
  padding-left: 28px;
}

/* ── Tabs ── */
.draft-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 24px;
}
.draft-tabs button {
  background: none;
  border: none;
  padding: 9px 16px 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-soft);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  border-radius: 0;
  transition: color 0.12s;
}
.draft-tabs button:hover { color: var(--ink); }
.draft-tabs button.active {
  color: var(--rose-deep);
  border-bottom-color: var(--rose-deep);
}

/* ── Editor ── */
.draft-editor { display: flex; flex-direction: column; gap: 4px; }

.draft-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 20px 0 10px;
}
.draft-section-header h3 {
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-soft);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── Role cards ── */
.draft-role-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 16px 12px;
  margin-bottom: 10px;
}
.draft-role-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.draft-role-label {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.draft-role-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
  margin-bottom: 10px;
}
@media (max-width: 600px) { .draft-role-grid { grid-template-columns: 1fr; } }

/* ── Bullets ── */
.draft-bullet-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 6px;
}
.draft-bullet-body { flex: 1; display: flex; flex-direction: column; gap: 3px; }
.draft-bullet-textarea {
  width: 100%;
  font-family: var(--font-body);
  font-size: 13px;
  color: var(--ink);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  resize: vertical;
  background: var(--surface);
  line-height: 1.5;
}
.draft-bullet-textarea:focus {
  outline: none;
  border-color: var(--rose);
  box-shadow: 0 0 0 2px var(--rose-soft);
}
.draft-add-bullet { margin-top: 4px; }

/* ── Paragraphs ── */
.draft-para-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
}
.draft-para-wrapper { position: relative; }
.para-remove {
  position: absolute;
  top: 28px;
  right: -30px;
}

/* ── Drag handle + remove ── */
.drag-handle {
  background: none;
  border: none;
  color: var(--ink-faint);
  font-size: 16px;
  cursor: grab;
  padding: 4px 2px;
  line-height: 1;
  touch-action: none;
  user-select: none;
}
.drag-handle:active { cursor: grabbing; }
.drag-handle.role-drag { padding-top: 2px; }
.draft-remove {
  background: none;
  border: none;
  color: var(--ink-faint);
  font-size: 18px;
  cursor: pointer;
  padding: 2px 6px;
  line-height: 1;
  border-radius: 6px;
  transition: color 0.12s;
}
.draft-remove:hover { color: var(--rose-deep); }

/* ── Letter ── */
.draft-limit-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12.5px;
  color: var(--ink-soft);
  margin-bottom: 10px;
}

/* ── Field counter ── */
.field-counter {
  font-size: 11.5px;
  color: var(--ink-faint);
  align-self: flex-end;
}
.field-counter.counter-warn { color: var(--butter-deep); }
.field-counter.counter-error { color: var(--rose-deep); font-weight: 600; }

/* ── Preview tab ── */
.preview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  height: 72vh;
}
.preview-grid iframe { width: 100%; height: 100%; border: 1px solid var(--border); border-radius: var(--radius-sm); }
@media (max-width: 700px) { .preview-grid { grid-template-columns: 1fr; } }

/* ── Listing tab ── */
.listing-preview {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 20px;
  max-height: 72vh;
  overflow-y: auto;
  color: var(--ink);
}

/* ── Reprompt modal modes ── */
.reprompt-modes {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.reprompt-modes legend { font-size: 12px; font-weight: 700; color: var(--ink-soft); padding: 0 4px; }
.reprompt-mode-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
}
.reprompt-mode-option input[type="radio"] { margin-top: 3px; }
.reprompt-mode-option strong { font-size: 13px; display: block; }

/* ── Draft modal (shared .draft-modal overrides the loading-card style) ── */
.draft-modal {
  background: var(--surface);
  border-radius: var(--radius);
  padding: 28px;
  max-width: 480px;
  width: calc(100% - 48px);
  box-shadow: var(--shadow);
}
.draft-modal h2 { font-size: 18px; margin-bottom: 6px; }
.draft-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}
```

- [ ] **Step 2: TypeScript check (no TS in CSS, just verify the file exists and is valid)**

```bash
ls /opt/angelica-jobhunt/dashboard/web/src/styles/draft.css
```

Expected: file listed.

- [ ] **Step 3: Commit**

```bash
cd /opt/angelica-jobhunt
git add dashboard/web/src/styles/draft.css
git commit -m "feat(frontend): add draft editor CSS"
```

---

### Task 10: DraftPage + main.tsx routing

**Files:**
- Create: `dashboard/web/src/pages/DraftPage.tsx`
- Modify: `dashboard/web/src/main.tsx`

**Interfaces:**
- Consumed: all components from Tasks 4-9
- `DraftPage` reads `?folder=` and `?jobId=` from `window.location.search`
- Internal types: `CvState` (from CVEditor), `LetterState` (from LetterEditor), `SortableRole` (from SortableRoleBlock)
- Helpers: `docToCvState(doc: DraftDoc): CvState`, `docToLetterState(doc: DraftDoc): LetterState`, `cvStateToPayload(cv: CvState): CvData`, `letterStateToPayload(letter: LetterState): LetterData`

- [ ] **Step 1: Write `DraftPage.tsx`**

```tsx
// dashboard/web/src/pages/DraftPage.tsx
import { useEffect, useState } from "react";
import "../styles/draft.css";
import { Grainient } from "../components/Grainient";
import { Loading } from "../components/Sprite";
import { DraftHeader } from "../components/draft/DraftHeader";
import { DraftTabs, type TabKey } from "../components/draft/DraftTabs";
import { CVEditor, type CvState } from "../components/draft/CVEditor";
import { LetterEditor, type LetterState } from "../components/draft/LetterEditor";
import { RepromptModal } from "../components/draft/RepromptModal";
import { DeleteModal } from "../components/draft/DeleteModal";
import {
  getDraft,
  saveDraft,
  buildApplication,
  markDraftReady,
  type DraftDoc,
  type CvData,
  type LetterData,
} from "../lib/api";
import type { SortableRole } from "../components/draft/SortableRoleBlock";

// ── Converters between API shape and sortable-state shape ──

function toSortableRole(r: { role: string; company: string; period: string; location: string; bullets: string[] }): SortableRole {
  return {
    id: crypto.randomUUID(),
    role: r.role ?? "",
    company: r.company ?? "",
    period: r.period ?? "",
    location: r.location ?? "",
    bullets: (r.bullets ?? []).map((text) => ({ id: crypto.randomUUID(), text })),
  };
}

function docToCvState(doc: DraftDoc): CvState {
  return {
    title: doc.cv.title ?? "",
    tagline: doc.cv.tagline ?? "",
    profile: doc.cv.profile ?? "",
    experience: (doc.cv.experience ?? []).map(toSortableRole),
    additional: (doc.cv.additional ?? []).map(toSortableRole),
  };
}

function docToLetterState(doc: DraftDoc): LetterState {
  return {
    subtitle: doc.letter.subtitle ?? "",
    paragraphs: (doc.letter.paragraphs ?? []).map((text) => ({ id: crypto.randomUUID(), text })),
  };
}

function cvStateToPayload(cv: CvState): CvData {
  return {
    max_pages: 2,
    title: cv.title,
    tagline: cv.tagline,
    profile: cv.profile,
    experience: cv.experience.map((r) => ({
      role: r.role, company: r.company, period: r.period, location: r.location,
      bullets: r.bullets.map((b) => b.text).filter(Boolean),
    })),
    additional: cv.additional.map((r) => ({
      role: r.role, company: r.company, period: r.period, location: r.location,
      bullets: r.bullets.map((b) => b.text).filter(Boolean),
    })),
  };
}

function letterStateToPayload(letter: LetterState): LetterData {
  return {
    max_pages: 1,
    subtitle: letter.subtitle,
    paragraphs: letter.paragraphs.map((p) => p.text).filter(Boolean),
  };
}

// ── Page component ──

export function DraftPage() {
  const params = new URLSearchParams(window.location.search);
  const folder = params.get("folder") ?? "";
  const jobId = params.get("jobId") ? Number(params.get("jobId")) : undefined;

  const [doc, setDoc] = useState<DraftDoc | null>(null);
  const [cvState, setCvState] = useState<CvState | null>(null);
  const [letterState, setLetterState] = useState<LetterState | null>(null);
  const [tab, setTab] = useState<TabKey>("cv");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [repromptOpen, setRepromptOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [loadError, setLoadError] = useState("");

  // Load draft on mount
  useEffect(() => {
    if (!folder) { setLoadError("No folder specified."); return; }
    getDraft(folder)
      .then((d) => {
        setDoc(d);
        setCvState(docToCvState(d));
        setLetterState(docToLetterState(d));
      })
      .catch((err) => setLoadError((err as Error).message));
  }, [folder]);

  function applyDoc(d: DraftDoc) {
    setDoc(d);
    setCvState(docToCvState(d));
    setLetterState(docToLetterState(d));
    setDirty(false);
  }

  async function handleSave() {
    if (!cvState || !letterState || !folder) return;
    setBusy(true);
    setStatusMsg("Saving…");
    try {
      const d = await saveDraft(folder, { cv: cvStateToPayload(cvState), letter: letterStateToPayload(letterState) });
      applyDoc(d);
      setStatusMsg("Draft saved.");
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleBuild() {
    if (!cvState || !letterState || !folder) return;
    // Save first, then build
    setBusy(true);
    setStatusMsg("Saving…");
    try {
      await saveDraft(folder, { cv: cvStateToPayload(cvState), letter: letterStateToPayload(letterState) });
      setStatusMsg("Building PDFs…");
      const result = await buildApplication(folder);
      setDoc((d) => d ? { ...d, artifact: result.artifact } : d);
      if (result.ok) {
        setStatusMsg("Build complete.");
        setTab("preview");
      } else {
        setStatusMsg(result.error ?? "Build failed.");
      }
      setDirty(false);
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleMarkReady() {
    if (!folder) return;
    setBusy(true);
    setStatusMsg("Marking as ready for review…");
    try {
      const d = await markDraftReady(folder, jobId);
      applyDoc(d);
      setStatusMsg("Marked as ready for review.");
    } catch (err) {
      setStatusMsg((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <div className="draft-page">
        <Grainient />
        <div className="draft-canvas">
          <p className="draft-error">{loadError}</p>
          <a className="btn ghost sm" href="/">← Dashboard</a>
        </div>
      </div>
    );
  }

  if (!doc || !cvState || !letterState) {
    return (
      <div className="draft-page">
        <Grainient />
        <Loading message="Loading draft…" />
      </div>
    );
  }

  return (
    <div className="draft-page">
      <Grainient />
      <DraftHeader
        folder={folder}
        dirty={dirty}
        busy={busy}
        onSave={handleSave}
        onBuild={handleBuild}
        onMarkReady={handleMarkReady}
        onReprompt={() => setRepromptOpen(true)}
        onDelete={() => setDeleteOpen(true)}
      />
      <div className="draft-canvas">
        {statusMsg && <p className="draft-status-msg">{statusMsg}</p>}
        {doc.warnings.length > 0 && (
          <ul className="draft-warnings">
            {doc.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        )}
        <DraftTabs active={tab} onChange={setTab} />
        {tab === "cv" && (
          <CVEditor
            cv={cvState}
            limits={doc.limits}
            onChange={(cv) => { setCvState(cv); setDirty(true); }}
          />
        )}
        {tab === "letter" && (
          <LetterEditor
            letter={letterState}
            limits={doc.limits}
            onChange={(letter) => { setLetterState(letter); setDirty(true); }}
          />
        )}
        {tab === "listing" && (
          <pre className="listing-preview">{doc.listing || "(No listing saved)"}</pre>
        )}
        {tab === "preview" && (
          doc.artifact?.has_cv || doc.artifact?.has_letter ? (
            <div className="preview-grid">
              {doc.artifact.has_cv && (
                <iframe title="CV preview" src={`/applications/${encodeURIComponent(folder)}/cv.pdf`} />
              )}
              {doc.artifact.has_letter && (
                <iframe title="Letter preview" src={`/applications/${encodeURIComponent(folder)}/motivation-letter.pdf`} />
              )}
            </div>
          ) : (
            <p className="draft-status-msg">Build the PDFs to preview them here.</p>
          )
        )}
      </div>

      {repromptOpen && (
        <RepromptModal
          folder={folder}
          jobId={jobId}
          currentCv={cvState}
          currentLetter={letterState}
          onSuccess={(d) => { applyDoc(d); setRepromptOpen(false); setStatusMsg("Draft reprompted."); }}
          onClose={() => setRepromptOpen(false)}
        />
      )}
      {deleteOpen && (
        <DeleteModal
          folder={folder}
          jobId={jobId}
          onSuccess={() => { window.location.href = "/"; }}
          onClose={() => setDeleteOpen(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update `main.tsx` to route `/draft` to `DraftPage`**

Read the current `main.tsx`:

```tsx
// Current content of dashboard/web/src/main.tsx (read before editing)
```

The current `main.tsx` (confirmed before writing the plan):

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/fraunces";
import "@fontsource-variable/hanken-grotesk";
import "@fontsource/dm-mono/400.css";
import "@fontsource/dm-mono/500.css";
import "./styles/tokens.css";
import "./styles/app.css";
import "./styles/odds.css";
import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Replace it with (add the `DraftPage` import and pathname branch):

```tsx
// dashboard/web/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/fraunces";
import "@fontsource-variable/hanken-grotesk";
import "@fontsource/dm-mono/400.css";
import "@fontsource/dm-mono/500.css";
import "./styles/tokens.css";
import "./styles/app.css";
import "./styles/odds.css";
import { App } from "./App";
import { DraftPage } from "./pages/DraftPage";

const element = (
  window.location.pathname === "/draft" ? <DraftPage /> : <App />
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{element}</React.StrictMode>,
);
```

- [ ] **Step 3: Full build**

```bash
cd /opt/angelica-jobhunt/dashboard/web && npm run build 2>&1
```

Expected: `✓ built in Xs` — clean TypeScript compilation, no errors.

- [ ] **Step 4: Restart the dashboard server and smoke-test**

```bash
pkill -f "python -m jobhunt" 2>/dev/null; sleep 1
cd /opt/angelica-jobhunt && python -m jobhunt dashboard &
sleep 2
curl -s http://localhost:8765/api/summary | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok', d.get('total_jobs','?'), 'jobs')"
```

Expected: `ok N jobs` (server running).

Then open a browser to `http://localhost:8765/draft?folder=<any-existing-folder>&jobId=1` and verify:
1. The React draft editor loads (not the old `draft.html` page)
2. CV tab shows filled form fields with char counters
3. Letter tab shows paragraphs with drag handles
4. Experience roles show drag handles
5. Dragging a role card reorders it
6. Save button activates after any edit
7. Reprompt button opens the mode-toggle modal
8. Delete button opens the confirmation modal

- [ ] **Step 5: Commit**

```bash
cd /opt/angelica-jobhunt
git add dashboard/web/src/pages/DraftPage.tsx dashboard/web/src/main.tsx
git add dashboard/web/src/components/draft/
git add dashboard/static/  # rebuilt output
git commit -m "feat(frontend): wire DraftPage as React route for /draft, retire vanilla JS editor"
```

---

## Verification Checklist

After all tasks are complete:

- [ ] `cd dashboard/web && npm run build` — clean, zero TypeScript errors
- [ ] `python -m jobhunt validate` — passes
- [ ] Navigate to `/draft?folder=<real-folder>&jobId=<id>` → React page loads, form pre-filled
- [ ] Drag an experience role up → Save → reload → order persisted
- [ ] Drag a bullet within a role → confirm within-role order maintained
- [ ] Reprompt → Fresh mode → new draft content appears (requires live Ollama)
- [ ] Reprompt → Refine mode + instructions → improved content appears
- [ ] Delete → folder gone from `Applications/`, job status reset in DB (`SELECT status FROM jobs WHERE id = <id>` → `reviewed`), navigates to `/`
- [ ] Navigate to `/draft?folder=...` (old URL) → React page loads (not `draft.html`)
- [ ] `curl -X DELETE http://localhost:8765/api/applications/NONEXISTENT` → returns 400 JSON error
- [ ] `curl -X POST http://localhost:8765/api/applications/FOLDER/reprompt -d '{"mode":"bad"}' -H 'Content-Type: application/json'` → 400 `mode must be 'fresh' or 'refine'`
