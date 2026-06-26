# Contour-Specific Topics

## Goal

Keep a single place for product topics that belong only to one documentation contour.

Use this file before adding or changing contour-sensitive text in `doc_diplo`. If a topic belongs only to one contour, keep it inside the correct conditional block or navigation condition.

## WCE-Only Topics

The portal functionality belongs only to WCE documentation.

Do not leave these topics in MS-targeted text:

- portal events
- Portal T1
- "Мой портал"
- portal manager
- portal organizer
- portal users
- portal reports
- organizer profile settings for portal access
- portal event publication and portal landing settings

In articles, keep this content inside `{% if domen == 'WCE' %}` blocks. In `toc.yaml`, use `when: domen == "WCE"`.

## MS-Only Topics

Paid-event functionality belongs only to MS documentation and must not appear in WCE-targeted text.

Use `wce-constraints.md` and `doc_agent/stop_words_checker-main/stopwords.txt` as the detailed source for WCE-forbidden paid-event wording.

Typical MS-only topics:

- tickets
- orders
- payments and payment reports
- promo codes
- tax status
- paid-event widgets

In articles, keep this content outside WCE output by using `{% if domen != 'WCE' %}` or an equivalent existing branch.

## Maintenance

Add new contour differences here when a review, Jira task, or product clarification introduces a recurring rule. Keep entries short and factual: topic, target contour, and where the content must be isolated.
