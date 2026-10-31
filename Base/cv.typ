// =============================================================================
// cv.typ — FROZEN CV layout. Agents edit the per-role YAML, never this file.
// Compile:  typst compile --root <workspace> Base/cv.typ <out.pdf> \
//             --input data=/Applications/<App>/cv-data.yaml \
//             --input profile=/config/profile.yaml
// (use Base/build.ps1 or jobhunt CLI — it wires this up for you)
// =============================================================================
#import "lib.typ": *

#let data = yaml(sys.inputs.data)
#let budget = data.at("max_pages", default: 2)
#let variant = data.at("variant", default: if budget <= 1 { "compact_one_page" } else { "classic_two_page" })
#let selected-highlights = data.at("selected_highlights", default: ())

#assert(
  variant == "grotesk_one_page" or variant == "compact_one_page" or variant == "classic_two_page" or variant == "enriched_two_page",
  message: "variant must be grotesk_one_page, compact_one_page, classic_two_page, or enriched_two_page."
)

// ---- Guard-rails (loud failures) -------------------------------------------
#assert(char-len(data.tagline) <= MAX_TAGLINE_CHARS,
  message: "tagline is " + str(char-len(data.tagline)) + " chars (max "
    + str(MAX_TAGLINE_CHARS) + "). Shorten it.")
#assert(char-len(data.profile) <= MAX_PROFILE_CHARS,
  message: "profile is " + str(char-len(data.profile)) + " chars (max "
    + str(MAX_PROFILE_CHARS) + "). Shorten it.")
#for r in data.experience { check-role(r) }
#for r in data.at("additional", default: ()) { check-role(r) }
#check-highlights(selected-highlights)

// ---- Dynamic candidate profile facts --------------------------------------
#let profile-path = sys.inputs.at("profile", default: none)
#let profile-data = if profile-path != none and profile-path != "" {
  yaml(profile-path)
} else {
  (:)
}
#let profile-data = if type(profile-data) == dictionary { profile-data } else { (:) }

// Missing or null profile keys render as empty; empty sections are hidden.
#let or-empty(value, empty) = if value == none { empty } else { value }
#let NAME = or-empty(profile-data.at("name", default: none), "")
#let CONTACT = or-empty(profile-data.at("contact", default: none), ())
#let SKILLS = or-empty(profile-data.at("skills", default: none), ())
#let LANGUAGES = or-empty(profile-data.at("languages", default: none), ())
#let EDUCATION = or-empty(profile-data.at("education", default: none), ())
#let CERTS = or-empty(profile-data.at("certifications", default: none), ())

// ---- Page setup -------------------------------------------------------------
#set page(paper: "a4", margin: page-margin, fill: page-bg,
  footer: context [
    #set text(size: 7.5pt, fill: muted)
    #align(center)[#NAME #h(4pt)|#h(4pt) CV #h(4pt)|#h(4pt)
      Page #counter(page).display() of #counter(page).final().first()]
  ])
#set text(font: body-font, size: 9.5pt, weight: body-weight, fill: ink, lang: "en")
#set par(justify: false, leading: 0.62em)

// ---- Full-bleed header band -------------------------------------------------
#place(top + left, dx: -page-margin, dy: -page-margin, block(
  width: 100% + 2 * page-margin, fill: cream, inset: (x: page-margin, y: 16pt))[
    #place(top + left, dx: -page-margin, block(width: 6pt, height: 86pt, fill: crimson))
    #text(font: heading-font, size: 25pt, weight: heading-weight, fill: ink)[#NAME]
    #v(-3pt)
    #text(size: 12pt, fill: muted)[#data.title]
    #v(4pt)
    #text(size: 9pt, fill: muted)[#data.tagline]
  ])
#v(92pt)

// ---- Shared blocks ----------------------------------------------------------
#let sidebar-full = [
  #if CONTACT.len() > 0 [
    #section("Contact")
    #for c in CONTACT { side-field(c.label, c.value, url: c.at("url", default: none)) }
  ]

  #if SKILLS.len() > 0 [
    #section("Core Skills")
    #for s in SKILLS { side-bullet(s) }
  ]

  #if LANGUAGES.len() > 0 [
    #section("Languages")
    #for lang in LANGUAGES {
      if type(lang) == array and lang.len() >= 2 {
        block(below: 7pt)[#text(size: 9.5pt, weight: "bold")[#lang.at(0)] \
          #text(size: 9pt, fill: muted)[#lang.at(1)]]
      } else if type(lang) == array and lang.len() == 1 {
        block(below: 7pt)[#text(size: 9.5pt, weight: "bold")[#lang.at(0)]]
      } else {
        block(below: 7pt)[#text(size: 9.5pt, weight: "bold")[#lang]]
      }
    }
  ]

  #if EDUCATION.len() > 0 [
    #section("Education")
    #for e in EDUCATION {
      block(below: 9pt)[
        #if "deg" in e { text(size: 9.5pt, weight: "bold")[#e.deg] }
        #if "school" in e [ \ #text(size: 8.5pt, fill: muted)[#e.school] ]
        #v(3pt)
        #for n in e.at("notes", default: ()) { side-bullet(n) }
      ]
    }
  ]
]

#let sidebar-compact = [
  #if CONTACT.len() > 0 [
    #section("Contact")
    #for c in CONTACT { side-field(c.label, c.value, url: c.at("url", default: none)) }
  ]

  #if SKILLS.len() > 0 [
    #section("Core Skills")
    #for s in SKILLS.slice(0, calc.min(SKILLS.len(), 8)) { side-bullet(s) }
  ]

  #if LANGUAGES.len() > 0 [
    #section("Languages")
    #for lang in LANGUAGES.slice(0, calc.min(LANGUAGES.len(), 4)) {
      if type(lang) == array and lang.len() >= 2 {
        block(below: 6pt)[#text(size: 9.2pt, weight: "bold")[#lang.at(0)] \
          #text(size: 8.6pt, fill: muted)[#lang.at(1)]]
      } else if type(lang) == array and lang.len() == 1 {
        block(below: 6pt)[#text(size: 9.2pt, weight: "bold")[#lang.at(0)]]
      } else {
        block(below: 6pt)[#text(size: 9.2pt, weight: "bold")[#lang]]
      }
    }
  ]

  #if EDUCATION.len() > 0 [
    #section("Education")
    #let e = EDUCATION.first()
    #if "deg" in e { text(size: 9.2pt, weight: "bold")[#e.deg] }
    #if "school" in e [ \ #text(size: 8.3pt, fill: muted)[#e.school] ]
  ]

  #if CERTS.len() > 0 [
    #section("Certifications")
    #for c in CERTS.slice(0, calc.min(CERTS.len(), 2)) { side-bullet(c) }
  ]
]

#let main-experience = [
  #section("Profile")
  #text(size: 9.5pt)[#data.profile]

  #if selected-highlights.len() > 0 [
    #section("Selected Impact")
    #bullets-list(selected-highlights)
  ]

  #section("Experience")
  #for r in data.experience {
    if r.at("include", default: true) { role-entry(r) }
  }
]

#let sidebar-grotesk-compact = [
  #for c in CONTACT { side-field(c.label, c.value, url: c.at("url", default: none)) }

  #if EDUCATION.len() > 0 [
    #section("Education")
    #let e = EDUCATION.first()
    #if "deg" in e { text(size: 9pt, weight: "bold")[#e.deg] }
    #if "school" in e [ \ #text(size: 8.2pt, fill: muted)[#e.school] ]
  ]

  #if SKILLS.len() > 0 [
    #section("Skills")
    #for s in SKILLS.slice(0, calc.min(SKILLS.len(), 8)) { side-bullet(s) }
  ]

  #if LANGUAGES.len() > 0 [
    #section("Languages")
    #for lang in LANGUAGES.slice(0, calc.min(LANGUAGES.len(), 4)) {
      if type(lang) == array and lang.len() >= 2 {
        block(below: 6pt)[#text(size: 9pt, weight: "bold")[#lang.at(0)] \
          #text(size: 8.4pt, fill: muted)[#lang.at(1)]]
      } else if type(lang) == array and lang.len() == 1 {
        block(below: 6pt)[#text(size: 9pt, weight: "bold")[#lang.at(0)]]
      } else {
        block(below: 6pt)[#text(size: 9pt, weight: "bold")[#lang]]
      }
    }
  ]

  #if CERTS.len() > 0 [
    #section("Certifications")
    #for c in CERTS.slice(0, calc.min(CERTS.len(), 2)) { side-bullet(c) }
  ]
]

#let compact-grotesk-role-entry(r) = block(width: 100%, breakable: false)[
  #text(font: heading-font, size: 10pt, weight: subheading-weight, fill: ink)[#r.role, #r.company] \
  #text(size: 8.1pt, fill: muted)[#r.period #h(3pt)|#h(3pt) #r.location]
  #v(2.6pt)
  #for b in r.bullets {
    grid(columns: (8pt, 1fr), column-gutter: 0pt,
      align(top)[#text(size: 8.6pt, fill: crimson)[•]],
      align(top)[#text(size: 8.6pt, fill: ink)[#b]])
    v(3.1pt, weak: true)
  }
  #v(4pt)
]

#let main-grotesk-compact = [
  #section("Summary")
  #text(size: 9.2pt)[#data.profile]

  #section("Experience")
  #let rendered-roles = (data.experience + data.at("additional", default: ())).filter(r => r.at("include", default: true))
  #for r in rendered-roles {
    compact-grotesk-role-entry(r)
  }
]

// ---- Variant layouts --------------------------------------------------------
#if variant == "grotesk_one_page" [
  #set text(font: body-font, size: 9.2pt, weight: body-weight, fill: ink, lang: "en")
  #set par(justify: false, leading: 0.52em)
  #grid(columns: (29%, 1fr), column-gutter: 18pt,
    sidebar-grotesk-compact,
    main-grotesk-compact,
  )
] else if variant == "compact_one_page" [
  #grid(columns: (30%, 1fr), column-gutter: 18pt,
    sidebar-compact,
    [
      #main-experience
      #let earlier = data.at("additional", default: ()).filter(r => r.at("include", default: true))
      #if earlier.len() > 0 [
        #for r in earlier { role-line(r) }
      ]
    ],
  )
] else [
  #grid(columns: (32%, 1fr), column-gutter: 22pt,
    sidebar-full,
    main-experience,
  )

  #let additional-roles = data.at("additional", default: ()).filter(r => r.at("include", default: true))
  #if CERTS.len() > 0 or selected-highlights.len() > 0 or additional-roles.len() > 0 [
    #pagebreak()
    #grid(columns: (32%, 1fr), column-gutter: 22pt,
      [
        #if CERTS.len() > 0 [
          #section("Certifications")
          #for c in CERTS { side-bullet(c) }
        ]
      ],
      [
        #if variant == "enriched_two_page" and selected-highlights.len() > 0 [
          #section("Selected Impact")
          #bullets-list(selected-highlights)
        ]
        #if additional-roles.len() > 0 [
          #section("Additional Experience")
          #for r in additional-roles {
            role-entry(r)
          }
        ]
      ],
    )
  ]
]

#assert-pages(budget)
