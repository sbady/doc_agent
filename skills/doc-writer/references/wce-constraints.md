# WCE Constraints

## Goal

Prevent WCE-targeted documentation from mentioning functionality that does not exist on WCE.

## Rule

If a feature exists only in MS, move it into a contour-specific block. Do not leave that wording in shared text.

## WCE-Sensitive Topics

WCE text should not contain references to paid or unavailable functionality such as:

- tickets
- orders
- promo codes
- tax status
- purchase
- price or cost
- gamification
- ratings
- networking
- generated links and related batch link generation flows

Treat the canonical source of forbidden wording as:

- `doc_agent/stop_words_checker-main/stopwords.txt`

## Validation

The stop words checker is not for drafting itself; it is a post-write or post-publication check when requested.

### Checker location

- `doc_agent/stop_words_checker-main/stopword_crawler.py`

### Typical use

Run only when the user asks to validate stop words.

Example command from the checker directory:

```bash
python stopword_crawler.py --max-pages 50 --output report.json
```

Or for one page:

```bash
python debug/check_single_page.py --path documentation/... --stop-words stopwords.txt
```

Before suggesting a WCE-safe article is ready, mentally screen it for obvious stop words even if the checker is not run.

## Writing Guidance

When writing shared text:

- prefer neutral wording that is valid in both contours
- branch only where the behavior or available controls differ

When writing WCE-only text:

- keep the wording free from paid-functionality concepts
- do not reuse MS phrasing blindly
