// =============================================================================
// lib.typ — Design system for CV + motivation letter.
// Agents must NOT edit this file. All tailoring happens in the per-role
// YAML data files. This file owns colours, fonts, spacing and the guard-rails
// that make over-long copy fail LOUDLY at compile time instead of silently
// breaking the layout.
// =============================================================================

// ---- Design tokens ----------------------------------------------------------
#let theme-path = sys.inputs.at("theme", default: none)
#let theme-data = if theme-path == none { (:) } else { yaml(theme-path) }
#let theme-enabled = theme-data.at("enabled", default: false) and not theme-data.at("fallback", default: false)
#let theme-color(key, fallback) = rgb(if theme-enabled { theme-data.at(key, default: fallback) } else { fallback })
#let theme-mode = if theme-enabled { theme-data.at("mode", default: "light") } else { "light" }
#let dark-mode = theme-mode == "dark"

#let crimson   = theme-color("accent", "#C41230")       // accent — Nike-CV deep crimson by default
#let ink       = theme-color("accent_dark", "#1A1A1A")  // body text
#let muted     = theme-color("muted", "#6B6B6B")        // meta / labels
#let cream     = theme-color("soft_bg", "#F1ECE2")      // header band
#let rule-grey = theme-color("rule", "#D9D4CC")
#let link-blue = theme-color("link", "#2A6F8E")         // clickable links
#let page-bg   = theme-color("page_bg", "#FFFFFF")

#let default-font-stack = ("Segoe UI", "Roboto")
#let configured-body-font = theme-data.at("body_font", default: ())
#let configured-heading-font = theme-data.at("heading_font", default: ())
#let theme-fonts-enabled = theme-enabled and theme-data.at("typography_enabled", default: false)
#let body-font = if theme-fonts-enabled and configured-body-font.len() > 0 { configured-body-font } else { default-font-stack }
#let heading-font = if theme-fonts-enabled and configured-heading-font.len() > 0 { configured-heading-font } else { body-font }

#let configured-body-weight = theme-data.at("body_weight", default: none)
#let configured-subheading-weight = theme-data.at("subheading_weight", default: none)
#let configured-heading-weight = theme-data.at("heading_weight", default: none)
#let body-weight = if theme-fonts-enabled and configured-body-weight != none { configured-body-weight } else { "regular" }
#let subheading-weight = if theme-fonts-enabled and configured-subheading-weight != none { configured-subheading-weight } else { "bold" }
#let heading-weight = if theme-fonts-enabled and configured-heading-weight != none { configured-heading-weight } else { "bold" }

#let page-margin = 1.5cm

// ---- Guard-rails (loud failures) --------------------------------------------
// Caps mirror the master CV. Break one → compile aborts with a fixable message.
#let MAX_BULLETS_PER_ROLE = 5
#let MAX_BULLET_CHARS      = 165   // ~2 printed lines in the main column
#let MAX_PROFILE_CHARS     = 600
#let MAX_TAGLINE_CHARS     = 170
#let MAX_HIGHLIGHTS        = 4
#let MAX_HIGHLIGHT_CHARS   = 135

// str.len()/str.slice() are BYTE-based in Typst; the Python validators count
// characters. Count codepoints so both layers agree (em-dashes and accents
// were inflating byte counts past the caps at legal char lengths, and the
// error message's slice(0, 50) crashed on a multibyte boundary).
#let char-len(s) = s.codepoints().len()
#let char-prefix(s, n) = s.codepoints().slice(0, calc.min(char-len(s), n)).join()

#let check-role(r) = {
  if r.at("include", default: true) {
    assert("bullets" in r and r.bullets.len() > 0,
      message: "Role '" + r.at("company", default: "?") + "' has no bullets.")
    assert(r.bullets.len() <= MAX_BULLETS_PER_ROLE,
      message: "Role '" + r.company + "' has " + str(r.bullets.len())
        + " bullets (max " + str(MAX_BULLETS_PER_ROLE) + "). Cut the weakest.")
    for b in r.bullets {
      assert(char-len(b) <= MAX_BULLET_CHARS,
        message: "A bullet under '" + r.company + "' is " + str(char-len(b))
          + " chars (max " + str(MAX_BULLET_CHARS) + "). Tighten it: \""
          + char-prefix(b, 50) + "...\"")
    }
  }
}

#let check-highlights(items) = {
  assert(items.len() <= MAX_HIGHLIGHTS,
    message: "selected_highlights has " + str(items.len())
      + " items (max " + str(MAX_HIGHLIGHTS) + "). Cut the weakest.")
  for h in items {
    assert(char-len(h) <= MAX_HIGHLIGHT_CHARS,
      message: "A selected_highlight is " + str(char-len(h))
        + " chars (max " + str(MAX_HIGHLIGHT_CHARS) + "). Tighten it: \""
        + char-prefix(h, 50) + "...\"")
  }
}

// Asserts the rendered doc is within its page budget. Overflow → louder than a
// silent third page: the build stops and tells the agent to cut copy.
#let assert-pages(budget) = context {
  let n = counter(page).final().first()
  assert(n <= budget,
    message: "Document grew to " + str(n) + " pages (budget " + str(budget)
      + "). Shorten profile/bullets or drop a role, then recompile.")
}

// ---- Components -------------------------------------------------------------
#let section(title) = block(width: 100%, above: 14pt, below: 7pt)[
  #text(font: heading-font, size: 9.5pt, weight: heading-weight, fill: crimson, tracking: 0.6pt)[
    #upper(title)
  ]
  #v(3pt, weak: true)
  #line(length: 100%, stroke: 0.6pt + rule-grey)
]

#let dot = text(fill: crimson, weight: "bold")[•]

#let bullets-list(items) = {
  for it in items {
    grid(columns: (10pt, 1fr), column-gutter: 0pt,
      align(top)[#dot], align(top)[#text(size: 9.5pt, fill: ink)[#it]])
    v(5.5pt, weak: true)
  }
}

// One job / experience entry.
#let role-entry(r) = block(width: 100%, breakable: false, below: 11pt)[
  #text(font: heading-font, size: 10.5pt, weight: subheading-weight, fill: ink)[#r.role, #r.company] \
  #text(size: 8.5pt, fill: muted)[#r.period #h(4pt)|#h(4pt) #r.location]
  #v(4pt)
  #bullets-list(r.bullets)
]

// Condensed role row for one-page "Earlier Experience" entries.
#let role-line(r) = block(width: 100%, below: 5pt)[
  #text(font: heading-font, size: 9.2pt, weight: subheading-weight, fill: ink)[#r.role, #r.company] \
  #text(size: 8pt, fill: muted)[#r.period #h(3pt)|#h(3pt) #r.location]
]

// Sidebar key/value (e.g. Email / address). If `url` is set, the value renders
// as a clickable link in the accent colour.
#let side-field(label, value, url: none) = block(below: 8pt)[
  #text(size: 8pt, fill: muted)[#label] \
  #if url == none {
    text(size: 9.5pt, fill: ink)[#value]
  } else {
    link(url)[#text(size: 9.5pt, fill: link-blue)[#value]]
  }
]

// Sidebar bulleted skill / cert line.
#let side-bullet(it) = grid(columns: (9pt, 1fr), row-gutter: 0pt,
  align(top)[#text(fill: crimson)[•]],
  align(top)[#text(size: 9pt, fill: ink)[#it]])
