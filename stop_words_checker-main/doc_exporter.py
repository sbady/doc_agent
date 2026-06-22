import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from crawler_core import TocEntry, crawl_urls, load_env_file, load_page_content


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export documentation corpus into cleaned article files for RAG."
    )
    parser.add_argument("--url", help="Стартовый URL документации")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Папка, в которую будет сохранен экспорт документации",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Задержка между запросами в секундах (по умолчанию 0.5)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Необязательно: ограничить количество посещаемых страниц",
    )
    parser.add_argument(
        "--env",
        dest="env_path",
        default=".env",
        help="Путь к .env файлу с параметром URL (по умолчанию .env)",
    )
    return parser.parse_args()


def normalize_space(text: str) -> str:
    return " ".join(text.split())


def block_title(note_type: str, fallback: str = "") -> str:
    titles = {
        "info": "Примечание",
        "note": "Примечание",
        "tip": "Совет",
        "warning": "Внимание",
        "alert": "Внимание",
        "caution": "Осторожно",
    }
    if fallback:
        return fallback
    return titles.get(note_type.lower(), "Примечание") if note_type else "Примечание"


def normalize_link(href: str, base_url: str) -> str:
    href = href.strip()
    parsed_base = urlsplit(base_url)
    site_root = f"{parsed_base.scheme}://{parsed_base.netloc}/"

    if href.startswith(("http://", "https://")):
        absolute = href
    elif href.startswith(("/", "./", "../")):
        absolute = urljoin(base_url, href)
    elif href.startswith(("ru/", "en/", "kz/", "by/")):
        absolute = urljoin(site_root, href)
    else:
        absolute = urljoin(base_url, href)

    parsed = urlsplit(absolute)
    return parsed.path.lstrip("/") or href


def cleanup_fragment(soup: BeautifulSoup) -> BeautifulSoup:
    for selector in ["a.yfm-anchor", ".yfm-clipboard-anchor", ".visually-hidden", "script", "style"]:
        for element in soup.select(selector):
            element.decompose()

    for image in soup.find_all("img"):
        image.decompose()

    return soup


def inline_text(node, base_url: str) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    classes = set(node.get("class", []))
    if "visually-hidden" in classes:
        return ""
    if node.name == "img":
        return ""
    if node.name == "a":
        if "yfm-anchor" in classes or "yfm-clipboard-anchor" in classes:
            return ""
        text = normalize_space("".join(inline_text(child, base_url) for child in node.children))
        href = node.get("href", "").strip()
        if not href:
            return text
        return f"[{text}]({normalize_link(href, base_url)})" if text else normalize_link(href, base_url)
    if node.name == "br":
        return "\n"
    return "".join(inline_text(child, base_url) for child in node.children)


def indent_block(block: str, indent: int) -> str:
    prefix = "  " * indent
    return "\n".join((prefix + line) if line else line for line in block.splitlines())


def render_list(list_tag: Tag, base_url: str, indent: int = 0) -> List[str]:
    lines: List[str] = []
    bullet = "- "
    for li in list_tag.find_all("li", recursive=False):
        nested_blocks: List[str] = []
        text_parts: List[str] = []

        for child in li.contents:
            if isinstance(child, NavigableString):
                text_parts.append(str(child))
                continue

            if not isinstance(child, Tag):
                continue

            child_classes = set(child.get("class", []))
            if child.name in ("ul", "ol"):
                nested_blocks.extend(render_list(child, base_url, indent + 1))
                continue
            if child.name == "details" and "yfm-cut" in child_classes:
                nested_blocks.extend(indent_block(block, indent + 1) for block in cut_blocks(child, base_url))
                continue
            if "yfm-note" in child_classes:
                nested_blocks.extend(indent_block(block, indent + 1) for block in note_blocks(child, base_url))
                continue
            if child.name in {"div", "section", "article", "table", "pre", "blockquote"}:
                nested_blocks.extend(indent_block(block, indent + 1) for block in render_blocks(child, base_url))
                continue

            text_parts.append(inline_text(child, base_url))

        text = normalize_space("".join(text_parts))
        if text:
            lines.append(("  " * indent) + bullet + text)
        lines.extend(nested_blocks)
    return lines


def note_blocks(element: Tag, base_url: str) -> List[str]:
    title_el = element.select_one(".yfm-note-title")
    content_el = element.select_one(".yfm-note-content")
    explicit_title = normalize_space(inline_text(title_el, base_url)) if title_el else ""
    note_type = str(element.get("note-type", "")).strip()
    title = block_title(note_type, explicit_title)

    blocks: List[str] = []
    if title:
        blocks.append(f"> {title}")

    target = content_el or element
    inner_blocks = render_blocks(target, base_url, skip_nodes={title_el} if title_el else None)
    for block in inner_blocks:
        for line in block.splitlines():
            blocks.append(f"> {line}" if line else ">")

    return blocks


def cut_blocks(element: Tag, base_url: str) -> List[str]:
    summary_el = element.find("summary")
    content_el = element.select_one(".yfm-cut-content")
    summary_text = normalize_space(inline_text(summary_el, base_url)) if summary_el else ""

    blocks: List[str] = []
    if summary_text:
        blocks.append(f"## {summary_text}")

    target = content_el or element
    blocks.extend(render_blocks(target, base_url, skip_nodes={summary_el} if summary_el else None))
    return blocks


def render_blocks(container: Tag, base_url: str, skip_nodes: Optional[set[Tag]] = None) -> List[str]:
    blocks: List[str] = []
    skipped = skip_nodes or set()

    for element in container.children:
        if isinstance(element, NavigableString):
            text = normalize_space(str(element))
            if text:
                blocks.append(text)
            continue

        if not isinstance(element, Tag):
            continue
        if element in skipped:
            continue

        classes = set(element.get("class", []))
        if element.name in {"script", "style"}:
            continue
        if element.name == "img":
            continue
        if "visually-hidden" in classes:
            continue

        if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(element.name[1])
            text = normalize_space(inline_text(element, base_url))
            if text:
                blocks.append(f'{"#" * level} {text}')
            continue

        if element.name in {"p", "blockquote"}:
            text = normalize_space(inline_text(element, base_url))
            if text:
                blocks.append(text)
            continue

        if element.name in {"ul", "ol"}:
            lines = render_list(element, base_url)
            if lines:
                blocks.append("\n".join(lines))
            continue

        if element.name == "pre":
            text = element.get_text("\n", strip=True)
            if text:
                blocks.append(f"```\n{text}\n```")
            continue

        if element.name == "table":
            text = normalize_space(element.get_text(" ", strip=True))
            if text:
                blocks.append(text)
            continue

        if element.name == "details" and "yfm-cut" in classes:
            inner_blocks = cut_blocks(element, base_url)
            if inner_blocks:
                blocks.extend(inner_blocks)
            continue

        if "yfm-note" in classes:
            inner_blocks = note_blocks(element, base_url)
            if inner_blocks:
                blocks.extend(inner_blocks)
            continue

        inner_blocks = render_blocks(element, base_url, skip_nodes=skipped)
        if inner_blocks:
            blocks.extend(inner_blocks)
            continue

        text = normalize_space(inline_text(element, base_url))
        if text:
            blocks.append(text)

    return blocks


def html_to_clean_markdown(fragment_html: str, base_url: str) -> str:
    soup = cleanup_fragment(BeautifulSoup(fragment_html, "html.parser"))
    blocks = render_blocks(soup, base_url)

    cleaned: List[str] = []
    prev = ""
    for block in blocks:
        if block and block != prev:
            cleaned.append(block)
        prev = block

    return "\n\n".join(cleaned).strip() + "\n"


def output_path_for_entry(output_dir: Path, entry: TocEntry) -> Path:
    href = entry.href or urlsplit(entry.url).path.lstrip("/")
    href = href.split("#", 1)[0].split("?", 1)[0]
    rel = Path(href)
    if rel.suffix.lower() == ".html":
        rel = rel.with_suffix(".md")
    elif not rel.suffix:
        rel = rel / "index.md"
    return output_dir / rel


def export_articles(start_url: str, output_dir: Path, delay: float, max_pages: Optional[int]) -> dict:
    session = requests.Session()
    entries, failed = crawl_urls(start_url, delay=delay, max_pages=max_pages)
    exported: List[dict] = []

    for entry in entries:
        page = load_page_content(entry.url, session)
        if not page:
            failed.append(entry.url)
            continue

        target = output_path_for_entry(output_dir, entry)
        target.parent.mkdir(parents=True, exist_ok=True)

        body = html_to_clean_markdown(page.html_fragment, page.url) if page.html_fragment else page.text.strip() + "\n"
        target.write_text(body, encoding="utf-8")

        exported.append(
            {
                "title": page.title,
                "url": page.url,
                "href": entry.href,
                "output_path": str(target.relative_to(output_dir)),
            }
        )

    manifest = {
        "start_url": start_url,
        "articles_exported": len(exported),
        "failed": failed,
        "articles": exported,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    args = parse_args()
    env_values = load_env_file(args.env_path)
    start_url = args.url or env_values.get("URL")

    if not start_url:
        print("Укажите стартовый URL через --url или URL в .env.", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = export_articles(
        start_url=start_url,
        output_dir=output_dir,
        delay=args.delay,
        max_pages=args.max_pages,
    )

    print(f"Экспортировано статей: {manifest['articles_exported']}")
    print(f"Папка экспорта: {output_dir}")
    if manifest["failed"]:
        print(f"Не удалось обработать страниц: {len(manifest['failed'])}")


if __name__ == "__main__":
    main()


