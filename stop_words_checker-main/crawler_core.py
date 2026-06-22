import html
import json
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, Tag


HEADERS = {"User-Agent": "DocCrawler/1.0 (+https://example.com)"}


@dataclass
class TocEntry:
    href: str
    url: str
    title: str = ""


@dataclass
class PageContent:
    url: str
    title: str
    text: str
    html_fragment: str


def load_env_file(path: str) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" not in stripped:
                    if stripped.startswith(("http://", "https://")) and "URL" not in data:
                        data["URL"] = stripped
                    continue
                key, value = stripped.split("=", 1)
                data[key.strip()] = value.strip()
    except FileNotFoundError:
        return data
    except OSError as exc:
        print(f"[WARN] Не удалось прочитать {path}: {exc}", file=sys.stderr)
    return data


def normalize_url(raw_url: str) -> Optional[str]:
    parsed = urlsplit(raw_url)
    if parsed.scheme not in ("http", "https"):
        return None

    path = parsed.path or "/"
    if path.endswith(("/index.html", "/index.htm")):
        path = path.rsplit("/", 1)[0] or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    normalized = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    return normalized


def scope_path(parsed_start) -> str:
    start_path = parsed_start.path or "/"
    if not start_path.endswith("/"):
        start_path = start_path.rsplit("/", 1)[0] + "/"
    return start_path


def is_probably_html(url: str) -> bool:
    path = urlsplit(url).path.lower()
    blocked_suffixes = (
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".zip",
        ".tar",
        ".gz",
        ".mp4",
        ".mp3",
    )
    return not any(path.endswith(ext) for ext in blocked_suffixes)


def fetch_page(url: str, session: requests.Session) -> Optional[requests.Response]:
    try:
        response = session.get(url, headers=HEADERS, timeout=10)
        if response.status_code >= 400:
            print(f"[WARN] Пропуск {url} — статус {response.status_code}", file=sys.stderr)
            return None
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            return None
        return response
    except requests.RequestException as exc:
        print(f"[WARN] Ошибка при загрузке {url}: {exc}", file=sys.stderr)
        return None


def extract_title(soup: BeautifulSoup, diplodoc_data: Optional[dict] = None) -> str:
    if diplodoc_data:
        title = diplodoc_data.get("data", {}).get("title")
        if title:
            return str(title).strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return "Без названия"


def choose_main_container(soup: BeautifulSoup) -> Tag:
    selectors = [
        "article",
        "main",
        "div[role=main]",
        "section[role=main]",
        "div#content",
        "div.content",
        "div#main",
        "div.main",
    ]
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            return element
    return soup.body or soup


def extract_diplodoc_fragment(soup: BeautifulSoup) -> Tuple[Optional[Tag], Optional[dict]]:
    script = soup.find("script", id="diplodoc-state")
    if not script or not script.string:
        return None, None
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return None, None
    html_fragment = data.get("data", {}).get("html")
    if not html_fragment:
        return None, data
    unescaped = html.unescape(html_fragment)
    fragment_soup = BeautifulSoup(unescaped, "html.parser")
    return fragment_soup, data


def collect_diplodoc_blocks_text(data: dict) -> Optional[str]:
    blocks = data.get("data", {}).get("data", {}).get("blocks", [])
    if not blocks:
        return None

    def gather(block_list: List[dict], acc: List[str]) -> None:
        for blk in block_list:
            for key in ("title", "description", "text"):
                val = blk.get(key)
                if val:
                    acc.append(html.unescape(str(val)))
            if "children" in blk and isinstance(blk["children"], list):
                gather(blk["children"], acc)
            if "items" in blk and isinstance(blk["items"], list):
                gather(blk["items"], acc)

    parts: List[str] = []
    gather(blocks, parts)
    if not parts:
        return None
    return BeautifulSoup(" ".join(parts), "html.parser").get_text(separator=" ", strip=True)


def parse_toc_entries(start_url: str, session: requests.Session) -> List[TocEntry]:
    parsed_start = urlsplit(start_url)
    base_for_toc = start_url if start_url.endswith("/") else f"{start_url}/"
    toc_url = urljoin(base_for_toc, "toc.js")
    site_root = f"{parsed_start.scheme}://{parsed_start.netloc}/"

    try:
        resp = session.get(toc_url, headers=HEADERS, timeout=10)
        if resp.status_code >= 400:
            return []
        content = resp.text
    except requests.RequestException:
        return []

    start = content.find("=")
    if start == -1:
        return []
    json_part = content[start + 1 :].strip()
    if json_part.endswith(";"):
        json_part = json_part[:-1]

    try:
        toc_data = json.loads(json_part)
    except json.JSONDecodeError:
        return []

    entries: List[TocEntry] = []

    def walk(node: dict) -> None:
        href = node.get("href")
        if href:
            absolute = urljoin(site_root, href)
            normalized = normalize_url(absolute)
            if normalized:
                entries.append(TocEntry(href=str(href), url=normalized, title=str(node.get("name", "")).strip()))
        for child_list_key in ("items", "children"):
            children = node.get(child_list_key)
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        walk(child)

    walk(toc_data)
    return entries


def extract_text(element: Tag) -> str:
    return element.get_text(separator=" ", strip=True)


def extract_links(element: Tag, base_url: str) -> List[str]:
    links: List[str] = []
    for anchor in element.find_all("a", href=True):
        href = anchor["href"]
        absolute = urljoin(base_url, href)
        normalized = normalize_url(absolute)
        if normalized:
            links.append(normalized)
    return links


def load_page_content(url: str, session: requests.Session) -> Optional[PageContent]:
    response = fetch_page(url, session)
    if not response:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    diplodoc_fragment, diplodoc_data = extract_diplodoc_fragment(soup)
    diplodoc_blocks_text = collect_diplodoc_blocks_text(diplodoc_data or {})

    if diplodoc_fragment:
        main_container = diplodoc_fragment
        text = extract_text(main_container)
    elif diplodoc_blocks_text:
        main_container = None
        text = diplodoc_blocks_text
    else:
        main_container = choose_main_container(soup)
        text = extract_text(main_container)

    title = extract_title(soup, diplodoc_data)
    html_fragment = str(main_container) if main_container is not None else ""
    return PageContent(url=url, title=title, text=text, html_fragment=html_fragment)


def crawl_urls(
    start_url: str, delay: float = 0.5, max_pages: Optional[int] = None
) -> Tuple[List[TocEntry], List[str]]:
    parsed_start = urlsplit(start_url)
    base_domain = parsed_start.netloc
    base_scope = scope_path(parsed_start)
    queue: Deque[TocEntry] = deque()
    visited: Set[str] = set()
    discovered: List[TocEntry] = []
    failed: List[str] = []
    session = requests.Session()

    normalized_start = normalize_url(start_url)
    if not normalized_start:
        print("Стартовый URL должен использовать http или https.", file=sys.stderr)
        return discovered, failed

    queue.append(TocEntry(href=urlsplit(normalized_start).path.lstrip("/"), url=normalized_start))

    toc_entries = parse_toc_entries(normalized_start, session)
    use_toc_links = bool(toc_entries)
    if use_toc_links:
        queue.clear()
        for entry in toc_entries:
            if entry.url not in visited and all(existing.url != entry.url for existing in queue):
                queue.append(entry)

    while queue:
        if max_pages and len(visited) >= max_pages:
            break

        current = queue.popleft()
        if current.url in visited:
            continue
        visited.add(current.url)
        discovered.append(current)

        if use_toc_links:
            time.sleep(delay)
            continue

        response = fetch_page(current.url, session)
        if not response:
            failed.append(current.url)
            time.sleep(delay)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        main_container = choose_main_container(soup)
        for link in extract_links(main_container, current.url):
            parsed_link = urlsplit(link)
            if parsed_link.netloc != base_domain:
                continue
            if not parsed_link.path.startswith(base_scope):
                continue
            if not is_probably_html(link):
                continue
            if link not in visited and all(existing.url != link for existing in queue):
                queue.append(TocEntry(href=parsed_link.path.lstrip("/"), url=link))

        time.sleep(delay)

    return discovered, failed
