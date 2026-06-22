# Exemplar Patterns

This file extracts stable patterns from the current exemplar articles so the skill does not need to re-infer them every time.

Source exemplars:

- `doc_diplo/src/ru/documentation/org_interface/settings/main_settings/registration/entry_form.md`
- `doc_diplo/src/ru/documentation/org_interface/settings/scene_setting.md`
- `doc_diplo/src/ru/documentation/org_interface/settings/landing.md`

## What To Reuse

Reuse:

- structural patterns
- rhythm of sections and subsections
- placement logic for screenshots and `cut` blocks
- amount of explanation per block
- contour branching style

Do not reuse:

- product details irrelevant to the current task
- old wording just because it already exists
- local formatting excesses that are not useful

## Stable Article Skeleton

Typical skeleton across the exemplars:

1. metadata frontmatter
2. `#` article title
3. optional short intro or note
4. `cut` block with interface location
5. top-level sections by interface block
6. subsections for concrete settings, behaviors, or actions
7. screenshots placed near the explanation, often inside `cut`

This means a new article should usually start from a practical interface orientation, not from abstract theory.

## Section Logic

The articles tend to group information by visible UI blocks:

- tab or page
- block inside the page
- settings inside the block

Within a section, the explanation usually follows one of two modes:

- short descriptive paragraph, then parameter list
- short orientation, then numbered action flow

Pick the mode that matches the actual interface behavior.

## Parameter Description Pattern

One recurring pattern in the exemplars is compact explanation of parameters and toggles:

- name of the setting
- what it changes for the user
- practical consequence
- warning or limitation only if necessary

Do not over-explain obvious controls.

## Screenshot Pattern

Screenshots are usually:

- placed in `cut` blocks
- tied to a nearby section
- split by contour when the interface differs
- used to show location or a dense configuration form

Good use:

- where to find a tab or control
- what a complex settings form looks like
- what differs between contours

Weak use:

- repeating a simple text statement the user already understands
- placing screenshots far from the relevant explanation

## Contour Branching Pattern

The exemplars show a restrained contour strategy:

- shared text first when behavior is common
- `{% if domen == 'WCE' %}` and `else` only where needed
- separate screenshots inside the contour branch

Do not branch entire sections unless the section is truly different between contours.

## Emphasis Pattern

The exemplars use emphasis, but the skill should apply it more selectively:

- bold is acceptable for critical labels, warnings, or exact UI terms
- italic works better for soft emphasis and in `cut` headings
- heavy bolding across many lines should be treated as legacy noise, not as a model to amplify

## Density Pattern

Good density in these articles is:

- enough detail to complete the action
- not overloaded with internal rationale
- broken into visible blocks

If a section becomes too long, split it by:

- settings group
- action stage
- viewer-facing vs organizer-facing behavior

## New Article Default Pattern

If there is no closer local pattern, use this default:

1. metadata
2. title
3. short intro
4. interface-location `cut`
5. main section by functional block
6. subsections for concrete options
7. note or warning only where the user can make a wrong choice

## Cleanup Guidance

When editing older articles, preserve working syntax but feel free to improve:

- overly loud formatting
- bloated paragraphs
- misplaced screenshots
- unnecessary branching

Do not refactor the whole article unless the task justifies it.
