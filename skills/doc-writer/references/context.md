# Product Context

## Product

Write user documentation for a platform used to run online and hybrid events.

Primary audiences:

- event organizers
- producers and moderators
- platform administrators in narrower cases
- participants only where the article explicitly targets them

Optimize for organizers first.

## Repositories

- `doc_diplo` — source code of the documentation on Diplodoc/YFM
- `doc_agent` — helper tooling for release notes, prompts, and QA

## Contours

Documentation is maintained for two similar product contours:

- `WCE` — open contour
- `MS` / `msh` — closed/internal contour

The same article may contain shared text plus conditional blocks for contour-specific behavior.

## Article Organization Principle

Organize articles by interface logic, not by backend logic.

Base the structure on:

- where the functionality is located in the interface
- how blocks are grouped on the page
- what sequence the user follows

The article should help the reader navigate the interface quickly.

## Exemplar Files

Use these as the first references when you need to infer local conventions:

- `doc_diplo/src/ru/documentation/org_interface/settings/main_settings/registration/entry_form.md`
- `doc_diplo/src/ru/documentation/org_interface/settings/scene_setting.md`
- `doc_diplo/src/ru/documentation/org_interface/settings/landing.md`

## Typical Tasks

- create a new article
- update an existing article from Jira context
- add or replace screenshots
- adapt wording for one contour only
- update `toc.yaml`
- prepare a documentation-ready draft for review
