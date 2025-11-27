from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from jinja2 import Template


def main() -> None:
    load_dotenv()

    # Default draft for demonstration (MSP-6209)
    draft = (
        'Перенесено поле "Короткое описание мероприятия" в раздел "Сцена" — '
        'теперь вводится в блоке "Информация для зрителя" и отображается во вкладке "Инфо"'
    )

    # Resolve template and glossary
    tmpl_path = Path(os.getenv("REFINE_PROMPT_PATH") or "prompt_templates/refine_release_summary.txt")
    tmpl_text = tmpl_path.read_text(encoding="utf-8")
    glossary_path = Path("docs/glossary/TERMS.md")
    glossary = glossary_path.read_text(encoding="utf-8") if glossary_path.exists() else ""

    prompt = Template(tmpl_text).render(draft=draft, glossary=glossary)
    print(prompt)


if __name__ == "__main__":
    main()
