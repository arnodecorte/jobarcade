// =============================================================================
// letter.typ — FROZEN motivation-letter layout (unified with the CV style).
// Agents edit the per-role YAML, never this file.
// Compile:  typst compile --root <workspace> Base/letter.typ <out.pdf> \
//             --input data=/Applications/<App>/letter-data.yaml \
//             --input profile=/config/profile.yaml
// (use Base/build.ps1 or jobhunt CLI — it wires this up for you)
// =============================================================================
#import "lib.typ": *

#let data = yaml(sys.inputs.data)
#let budget = data.at("max_pages", default: 1)

// ---- Guard-rails ------------------------------------------------------------
#assert(data.paragraphs.len() >= 2 and data.paragraphs.len() <= 6,
  message: "letter has " + str(data.paragraphs.len())
    + " paragraphs (keep 3-5). Merge or split.")
// Soft proxy for "near one page"; the page-count assert below is the real guard.
#let total = data.paragraphs.fold(0, (a, p) => a + char-len(p))
#assert(total <= 2050,
  message: "letter body is " + str(total)
    + " chars (max 2050 → one page). Trim a paragraph.")

// ---- Dynamic candidate profile facts --------------------------------------
#let profile-path = sys.inputs.at("profile", default: none)
#let profile-data = if profile-path != none and profile-path != "" {
  yaml(profile-path)
} else {
  (:)
}

#let NAME = profile-data.at("name", default: "Candidate Name")

#set page(paper: "a4", margin: 2cm, fill: page-bg)
#set text(font: body-font, size: 10.5pt, weight: body-weight, fill: ink, lang: "en")
#set par(justify: false, leading: 0.7em, spacing: 1.0em)

// ---- Header -----------------------------------------------------------------
#align(center)[
  #text(font: heading-font, size: 24pt, weight: heading-weight, fill: ink)[#NAME]
  #v(4pt)
  #line(length: 38%, stroke: 1.4pt + crimson)
  #v(4pt)
  #text(size: 11pt, fill: muted)[#data.subtitle]
]
#v(18pt)

// ---- Body -------------------------------------------------------------------
Dear Hiring Manager,
#v(4pt)

#for p in data.paragraphs [
  #p
  #parbreak()
]

#v(6pt)
Kindest regards,
#v(2pt)
#let signature-path = profile-data.at("signature", default: none)
#if signature-path != none {
  image(signature-path, height: 52pt)
} else {
  image(if dark-mode { "assets/signature-white.png" } else { "assets/signature.png" }, height: 52pt)
}
#text(size: 10.5pt)[#NAME]

#context {
  let n = counter(page).final().first()
  assert(n <= budget, message: "letter spilled to " + str(n)
    + " pages. Trim the body.")
}
