# Style Guide

## Tone

Write in a calm, practical, user-facing style.

Prefer:

- clear verbs
- present tense
- short paragraphs
- step-by-step instructions where the user performs actions

Avoid:

- internal engineering language that is not useful to the reader
- decorative wording
- explanation of implementation details unless they change user behavior

## Formatting

Use Diplodoc/YFM patterns already present in nearby articles.

### Emphasis

Use emphasis sparingly:

- use `**bold**` only for truly critical controls, warnings, or labels that must stand out
- use `*italic*` more often for softer emphasis
- avoid over-highlighting because too much bold text breaks visual focus and makes the page harder to scan

Too much bold is considered noise. Bold should help the reader notice an important point, not turn the whole section into a visual accent.

### Lists

For numbered and bulleted lists:

- by default, do not put periods at the end of list items
- keep list items visually light and compact
- if a local article already contains a stable list pattern, preserve the surrounding style unless the task explicitly requires cleanup

### Quotes

Use only straight quotes:

- `"..."`, not typographic curly quotes

### Headings

Use headings to mirror the interface:

- article title
- major block or tab
- subsection for concrete settings or actions

Do not create deep heading hierarchies without need.

### Notes

Use notes only when they add real value:

- `info` for context or clarification
- `warning` or `alert` for risk or user-facing limitation
- `tip` when it actually simplifies user work

Do not wrap ordinary information in note blocks.

### Cuts

Use `cut` blocks for:

- screenshots of location in interface
- secondary detail that is helpful but not required on first read
- bulky illustrations that would otherwise overload the page

## Article Shape

Typical article pattern:

1. metadata block
2. `#` title
3. short orientation paragraph or note if needed
4. major sections by interface block
5. screenshots or `cut` blocks near the relevant explanation
6. warnings only where the user can make a wrong decision

## Screenshots And Assets

Keep screenshots close to the section they explain.

When replacing or adding screenshots:

- preserve local path conventions
- use contour-specific image branches if interfaces differ
- avoid adding screenshots that repeat text without clarifying anything

## Accuracy Rule

Do not invent:

- names of controls
- system behavior
- visibility of options
- contour differences

If the context is incomplete, return a draft plus `Требует уточнения:`.

