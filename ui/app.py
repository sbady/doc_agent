from __future__ import annotations

import html as htmllib
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
MAIN_SCRIPT = ROOT_DIR / "main.py"
SANITIZER_SCRIPT = ROOT_DIR / "scripts" / "check_sanitizer.py"
STOPWORDS_SCRIPT = ROOT_DIR / "stop_words_checker-main" / "stopword_crawler.py"
STOPWORDS_DEFAULT = ROOT_DIR / "stop_words_checker-main" / "stopwords.txt"
ARTICLE_PROMPT_PATH = ROOT_DIR / "prompt_templates" / "article_update_from_jira.txt"


@dataclass
class CommandResult:
    command: List[str]
    code: int
    stdout: str
    stderr: str
    elapsed_sec: float


LOG_PREFIX_RE = re.compile(r"^(?:OUTPUT:)?\d{4}-\d{2}-\d{2}\s")


def init_page() -> None:
    st.set_page_config(page_title="Release Notes Studio", page_icon="RN", layout="wide")
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap');

            :root {
                --bg: #f6f9f6;
                --panel: #ffffff;
                --text: #1d2a1d;
                --muted: #526252;
                --accent: #1f6a43;
                --accent-2: #145a37;
                --accent-soft: #e6f4ec;
                --warn: #9a3a16;
                --warn-soft: #fff2ea;
                --border: #d7e1d7;
            }

            .stApp {
                background:
                    radial-gradient(1200px 500px at -10% -10%, #dff0e4 0%, transparent 60%),
                    radial-gradient(900px 450px at 110% -5%, #f2eadf 0%, transparent 60%),
                    var(--bg);
                color: var(--text) !important;
                font-family: "IBM Plex Sans", sans-serif;
            }

            .block-title {
                font-family: "Space Grotesk", sans-serif;
                font-weight: 700;
                letter-spacing: .2px;
                margin: 0 0 8px 0;
                color: var(--text) !important;
            }

            .card {
                background: var(--panel);
                border: 1px solid var(--border);
                border-radius: 14px;
                padding: 14px 16px;
                box-shadow: 0 8px 25px rgba(22, 36, 24, .06);
                margin-bottom: 12px;
            }

            .subtle {
                color: var(--muted) !important;
                font-size: .94rem;
            }

            .warn {
                background: var(--warn-soft);
                border: 1px solid #f5cbb7;
                border-left: 4px solid var(--warn);
                border-radius: 10px;
                padding: 10px 12px;
                margin: 8px 0 12px 0;
                color: #6f2a12 !important;
            }

            .ok {
                background: var(--accent-soft);
                border: 1px solid #b8deca;
                border-left: 4px solid var(--accent);
                border-radius: 10px;
                padding: 10px 12px;
                margin: 8px 0 12px 0;
                color: #184f33 !important;
            }

            /* Base text visibility */
            .stMarkdown, .stMarkdown *, .stText, .stCaption, p, li, h1, h2, h3, h4, h5, h6, label {
                color: var(--text);
            }

            /* Tabs */
            button[role="tab"] {
                color: var(--text) !important;
                background: #edf3ed !important;
                border: 1px solid #d6e0d6 !important;
                border-radius: 10px !important;
                margin-right: 6px !important;
                font-weight: 600 !important;
                padding: 10px 18px !important;
                min-height: 44px !important;
            }

            button[role="tab"][aria-selected="true"] {
                background: #ddf0e5 !important;
                border-color: #9dceaf !important;
                color: #123f29 !important;
            }

            /* Expander */
            [data-testid="stExpander"] {
                background: #f9fcf9;
                border: 1px solid var(--border);
                border-radius: 10px;
                margin-bottom: 8px;
            }

            [data-testid="stExpander"] details summary {
                background: #f4f9f4 !important;
                color: var(--text) !important;
                border-radius: 10px;
                padding: 6px 10px;
            }

            [data-testid="stExpander"] details[open] summary {
                background: #edf6ef !important;
                color: var(--text) !important;
            }

            /* Widgets */
            [data-testid="stWidgetLabel"] p {
                color: var(--text) !important;
                font-weight: 600;
            }

            [data-baseweb="input"] input,
            [data-baseweb="textarea"] textarea {
                background: #ffffff !important;
                color: var(--text) !important;
            }

            [data-baseweb="select"] * {
                color: var(--text) !important;
            }

            [data-baseweb="select"] > div,
            [data-baseweb="select"] [role="button"] {
                background: #ffffff !important;
                border-color: #d6e0d6 !important;
                color: var(--text) !important;
            }

            div[role="listbox"] {
                background: #ffffff !important;
                border: 1px solid #d6e0d6 !important;
            }

            div[role="option"] {
                background: #ffffff !important;
                color: var(--text) !important;
            }

            div[role="option"][aria-selected="true"] {
                background: #e8f4eb !important;
                color: #123f29 !important;
            }

            /* Buttons */
            .stButton > button {
                background: var(--accent) !important;
                color: #ffffff !important;
                border: 1px solid var(--accent-2) !important;
                border-radius: 10px !important;
                font-weight: 600 !important;
            }

            .stButton > button * {
                color: #ffffff !important;
                fill: #ffffff !important;
            }

            .stButton > button:hover {
                background: var(--accent-2) !important;
                color: #ffffff !important;
            }

            code {
                background: #edf5ef !important;
                color: #174630 !important;
                border: 1px solid #d2e2d6;
                border-radius: 6px;
                padding: 1px 6px;
            }

            pre, code {
                color: var(--text) !important;
            }

            .logbox {
                border-radius: 10px;
                border: 1px solid #d7e1d7;
                padding: 10px 12px;
                margin: 4px 0;
                max-height: 360px;
                overflow: auto;
            }

            .logbox pre {
                margin: 0;
                white-space: pre-wrap;
                word-break: break-word;
                color: #1d2a1d !important;
                font-size: 12px;
                line-height: 1.35;
                font-family: "IBM Plex Sans", sans-serif;
            }

            .log-ok {
                background: #eef8f1;
                border-color: #cde4d3;
            }

            .log-err {
                background: #fff1ef;
                border-color: #f1cbc5;
            }

            /* Streamlit top-right menu visibility */
            [data-testid="stToolbar"] button, [data-testid="stToolbar"] svg {
                color: var(--text) !important;
                fill: var(--text) !important;
            }

            /* Metrics readability */
            [data-testid="stMetricValue"] {
                color: #1d2a1d !important;
            }

            [data-testid="stMetricLabel"] {
                color: #334533 !important;
            }

            [data-testid="stMetricDelta"] {
                color: #1d2a1d !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def load_article_prompt() -> str:
    if ARTICLE_PROMPT_PATH.exists():
        return ARTICLE_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return (
        "Ты — технический писатель. Обнови статью документации по изменениям из Jira-задачи.\n\n"
        "Вход:\n"
        "1) Исходный текст статьи (полный markdown/исходный код)\n"
        "2) Описание Jira-задачи\n"
        "3) Важные комментарии\n\n"
        "Требования:\n"
        "- сохраняй структуру и форматирование;\n"
        "- меняй только подтвержденные части;\n"
        "- не добавляй неподтвержденные детали;\n"
        "- при нехватке данных добавляй блок 'Требует уточнения'.\n"
    )


def run_command(args: List[str], timeout_sec: int = 3600) -> CommandResult:
    start = time.time()
    process = subprocess.run(
        args,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
    )
    return CommandResult(
        command=args,
        code=process.returncode,
        stdout=process.stdout or "",
        stderr=process.stderr or "",
        elapsed_sec=time.time() - start,
    )


def run_command_live(args: List[str], timeout_sec: int = 3600, tail_lines: int = 20) -> CommandResult:
    start = time.time()
    process = subprocess.Popen(
        args,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    all_lines: List[str] = []
    tail: List[str] = []
    live_box = st.empty()

    try:
        while True:
            if time.time() - start > timeout_sec:
                process.kill()
                raise subprocess.TimeoutExpired(args, timeout_sec)

            line = process.stdout.readline() if process.stdout is not None else ""
            if line:
                stripped = line.rstrip("\n")
                all_lines.append(stripped)
                tail.append(stripped)
                if len(tail) > tail_lines:
                    tail = tail[-tail_lines:]
                live_box.text_area(
                    f"Логи (последние {tail_lines} строк, обновляется во время выполнения)",
                    value="\n".join(tail),
                    height=220,
                )
            elif process.poll() is not None:
                break
            else:
                time.sleep(0.05)

        # дочитать хвост буфера после завершения
        remainder = process.stdout.read() if process.stdout is not None else ""
        if remainder:
            for ln in remainder.splitlines():
                all_lines.append(ln)
                tail.append(ln)
            if len(tail) > tail_lines:
                tail = tail[-tail_lines:]
            live_box.text_area(
                f"Логи (последние {tail_lines} строк, обновляется во время выполнения)",
                value="\n".join(tail),
                height=220,
            )
    except subprocess.TimeoutExpired:
        return CommandResult(
            command=args,
            code=124,
            stdout="\n".join(all_lines),
            stderr=f"Превышен таймаут выполнения: {timeout_sec} сек.",
            elapsed_sec=time.time() - start,
        )

    return CommandResult(
        command=args,
        code=process.returncode if process.returncode is not None else 1,
        stdout="\n".join(all_lines),
        stderr="",
        elapsed_sec=time.time() - start,
    )


def render_log_block(text: str, *, kind: str) -> None:
    css_class = "log-ok" if kind == "ok" else "log-err"
    escaped = htmllib.escape(text)
    st.markdown(
        f"<div class='logbox {css_class}'><pre>{escaped}</pre></div>",
        unsafe_allow_html=True,
    )


def extract_issue_short_text(stdout: str, stderr: str = "") -> str:
    combined = (stdout or "") + "\n" + (stderr or "")
    lines = [ln.strip() for ln in combined.splitlines() if ln.strip()]
    if not lines:
        return ""

    # 1) Try to parse "Summary preview: ..."
    for ln in reversed(lines):
        marker = "Summary preview:"
        pos = ln.find(marker)
        if pos >= 0:
            tail = ln[pos + len(marker) :].strip()
            if tail:
                return tail

    # 2) Last non-log line.
    candidates: List[str] = []
    for ln in lines:
        if LOG_PREFIX_RE.match(ln):
            continue
        if "Total prompt characters sent to LLM" in ln:
            continue
        candidates.append(ln)
    if candidates:
        return candidates[-1]

    # 3) Fallback.
    return lines[-1]


def extract_changelog_text(stdout: str, stderr: str = "") -> str:
    combined = ((stdout or "") + "\n" + (stderr or "")).strip()
    if not combined:
        return ""
    lines = combined.splitlines()

    start_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("Что было сделано:"):
            start_idx = i
            break
    if start_idx is None:
        return combined

    out = lines[start_idx:]
    while out and (LOG_PREFIX_RE.match(out[-1].strip()) or "Total prompt characters sent to LLM" in out[-1]):
        out.pop()
    return "\n".join(out).strip()


def add_history(entry: Dict[str, Any]) -> None:
    history = st.session_state.setdefault("run_history", [])
    history.insert(0, entry)
    st.session_state["run_history"] = history[:30]


def render_result(name: str, result: CommandResult, extra: Optional[Dict[str, Any]] = None) -> None:
    status = "Успех" if result.code == 0 else "Ошибка"
    status_class = "ok" if result.code == 0 else "warn"
    st.markdown(
        f"<div class='{status_class}'><b>{status}</b> • {name} • {result.elapsed_sec:.1f} c</div>",
        unsafe_allow_html=True,
    )
    st.caption("Команда: " + " ".join(result.command))

    if result.stdout.strip():
        with st.expander("stdout (полный лог)", expanded=False):
            render_log_block(result.stdout, kind=("ok" if result.code == 0 else "err"))
    if result.stderr.strip():
        with st.expander("stderr (полный лог)", expanded=(result.code != 0)):
            render_log_block(result.stderr, kind="err")

    add_history(
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": name,
            "code": result.code,
            "elapsed": round(result.elapsed_sec, 2),
            "extra": extra or {},
        }
    )


def execute_command_ui(
    action_name: str,
    args: List[str],
    *,
    timeout_sec: int = 3600,
    live_debug: bool = False,
) -> CommandResult:
    with st.status(f"Запуск: {action_name}", expanded=live_debug) as status:
        if live_debug:
            result = run_command_live(args, timeout_sec=timeout_sec, tail_lines=20)
        else:
            with st.spinner("Выполняется команда..."):
                result = run_command(args, timeout_sec=timeout_sec)

        if result.code == 0:
            status.update(label=f"Готово: {action_name}", state="complete")
        else:
            status.update(label=f"Ошибка: {action_name}", state="error")

    render_result(action_name, result)
    return result


def copy_to_clipboard_native(text: str) -> Tuple[bool, str]:
    try:
        import tkinter as tk  # local import to avoid hard dependency at import time

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True, "Скопировано в буфер обмена."
    except Exception as exc:
        return False, f"Не удалось скопировать автоматически ({exc}). Выдели текст и нажми Ctrl+C."


def clipboard_button(label: str, text: str, key: str) -> None:
    if st.button(label, key=f"copy_{key}", use_container_width=False):
        ok, msg = copy_to_clipboard_native(text)
        if ok:
            st.success(msg)
        else:
            st.warning(msg)


def show_overview() -> None:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h3 class='block-title'>Обзор процесса</h3>", unsafe_allow_html=True)
    st.markdown(
        """
Документация включает два основных процесса:

1. **Актуализация документации релиза** — подготовка релизных заметок и фиксация задач на обновление статей.  
2. **Создание/изменение статей** — обновление документации по согласованным задачам и публикация.
        """
    )
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Подробный процесс актуализации документации", expanded=True):
        st.markdown(
            """
## Актуализация документации релиза
Работа с документацией релиза привязана непосредственно к релизу продукта, для которого ведется документация. Этот процесс включает в себя создание *релизных заметок* (краткое описание задач) и *задач на создание/изменений статей*. Процесс можно разбить на несколько ключевых этапов:

1. **Создание задачи актуализации документации релиза**  
   В момент выхода релиза, который включает обновления, исправления или доработки продукта, создается задача по шаблону "*✒️ Актуализация документации релиза*".

2. **Использование шаблона задачи**  
   Для каждой задачи актуализации документации используется заранее подготовленный шаблон. Этот шаблон автоматически создает таблицу релиза. Таблица релиза служит для указания краткого описания каждой задачи релиза, отражая изменения, которые были внесены в продукт.

3. **Заполнение таблицы релиза**  
   В таблице для каждой задачи из релиза указывается краткое описание того, что было сделано. Эти краткие описания формируют релизные заметки, которые затем публикуются в документации продукта в разделе "Релизы". В разделе фиксируются все изменения, доработки, исправления багов и других аспектов, связанных с релизом.

4. **Отслеживание изменений в статьях**  
   В таблице релиза также помечаются задачи, которые требуют изменения существующих статей или создания новых. Например, если релиз изменяет логику авторизации, то необходимо обновить статью, описывающую этот процесс. Каждая задача, которая затрагивает статью, отмечается в таблице в отдельном столбце "мануал", чтобы выделить задачи, требующие изменений в статьях.

5. **Согласование таблицы релиза**  
   Когда все задачи релиза заносятся в таблицу и проверяются на необходимость создания или изменения статей, таблица согласовывается с менеджером продукта или другим ответственными лицом. После этого она публикуется в разделе "Релизы" документации, отражая все изменения.

6. **Создание задач на изменения статей**  
   Если задачи требуют изменений в статьях, создаются новые задачи на основе шаблона "✒️ Создание/изменение статьи".

## Создание/изменение статей
Процесс создания и изменения статей обычно связан с релизами и задачами на актуализацию документации релиза.

1. **Создание задачи на создание/изменение статьи**
   - После того как в задаче "*✒️ Актуализация документации релиза*" отмечены задачи, требующие изменения или создания статей, создаются соответствующие задачи на создание/изменение статьи.
   - В случае, если несколько задач влияют на одну статью или один логический блок, эти задачи можно объединить в одну задачу для удобства.

2. **Тип задачи**
   - Задача создается по шаблону "*✒️ Актуализация документации релиза*".
   - В задаче указывается тип задачи: создание новой статьи или обновление существующей.
   - Также описывается, что именно изменилось в продукте (краткое описание задачи из релизной таблицы).

3. **Публикация изменений на dev-стенд**
   - После того как изменения были внесены в статью, она публикуется на dev-стенде документации для предварительного согласования.
   - В комментариях к задаче добавляется ссылка на обновленную статью с кратким описанием изменений, чтобы проверяющие могли быстро понять, что именно было изменено.

4. **Согласование и правки**
   - После публикации на dev-стенде статья проверяется ответственным лицом (обычно продакт-менеджером или аналитиком).
   - Для этого задача переводится в статус "Analytics Review" и передается ответственному лицу.
   - Если нужно внести правки, они описываются в комментариях проверяющим, и задача возвращается на доработку техническому писателю.
   - Техпис вносит правки, повторно публикует изменения на dev-стенд, возвращает задачу на проверку проверяющему.

5. **Заключительная проверка и публикация**
   - После окончательного согласования задача передается на публикацию на PROD стенд документации.
   - Когда все согласования завершены, задача закрывается.
            """
        )

    with st.expander("Промпт для обновления статьи по Jira-задаче", expanded=False):
        st.markdown(
            """
Инструкция по использованию:
1. Возьми промпт ниже и вставь его в языковую модель.
2. Вставь полный исходный текст статьи (с форматированием).
3. Вставь описание Jira-задачи и важные комментарии.
4. Проверь, что задача действительно относится к этой статье.
5. Получи обновленный текст, проведи быстрый аудит и подготовь к публикации.
            """
        )
        prompt_text = st.session_state.get("article_prompt_text") or load_article_prompt()
        st.session_state["article_prompt_text"] = prompt_text
        current_prompt = st.text_area("Промпт", value=prompt_text, height=260, key="article_prompt_view")
        st.session_state["article_prompt_text"] = current_prompt
        clipboard_button("Скопировать промпт", current_prompt, "article_prompt")


def release_notes_tools() -> None:
    st.markdown("<h3 class='block-title'>Релизные заметки</h3>", unsafe_allow_html=True)
    st.markdown(
        "<p class='subtle'>Все функции независимы. Можно запускать любую отдельно.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("B1. Заполнение релизной таблицы в Jira")
    with st.expander("Что делает и что подготовить", expanded=False):
        st.markdown(
            """
Подготовка:
- Создай задачу по шаблону **✒️ Актуализация документации релиза**.
- Укажи ее ключ как `release target`.
- Укажи релизную задачу-источник как `release parent`.

Результат:
- таблица в `release target` будет заполнена/обновлена;
- колонки `Шаблоны` и `Мануал` сохраняются.
            """
        )
    parent_key_fill = st.text_input("Release parent", placeholder="MSP-7000", key="b2_parent")
    target_key_fill = st.text_input("Release target", placeholder="MSP-8000", key="b2_target")
    b2_log_level = st.selectbox("Уровень логов", ["INFO", "DEBUG"], index=0, key="b2_log_level")
    st.markdown(
        "<div class='warn'><b>Внимание:</b> будет изменено описание задачи <code>release target</code> в Jira.</div>",
        unsafe_allow_html=True,
    )
    if st.button("Заполнить таблицу", key="b2_run", use_container_width=True):
        if not parent_key_fill.strip() or not target_key_fill.strip():
            st.error("Укажи и release parent, и release target.")
        else:
            args = [
                sys.executable,
                str(MAIN_SCRIPT),
                "--release-parent",
                parent_key_fill.strip(),
                "--release-target",
                target_key_fill.strip(),
                "--mode",
                "fill",
                "--log-level",
                b2_log_level,
            ]
            execute_command_ui(
                "B1: заполнение релизной таблицы",
                args,
                timeout_sec=3600,
                live_debug=(b2_log_level == "DEBUG"),
            )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("B2. Готовый текст для вставки в исходный код документации")
    with st.expander("Что делает", expanded=False):
        st.markdown(
            """
Пайплайн:
1. На вход подается `release target` с уже заполненной релизной таблицей.
2. Таблица парсится построчно (сохраняется порядок строк).
3. Строки группируются по стендам/типам задач и раскладываются по условным блокам:
   - общий блок;
   - `{% if domen == 'WCE' %}`;
   - `{% else %}`.
4. На выходе формируется готовый `changelog`-текст для вставки в исходный код документации.

Важно:
- Красный фрагмент в wiki-макросе `{color:#de350b}...{color}` трактуется как *MS-only*.
- Такой фрагмент автоматически оборачивается в `{% if domen != 'WCE' %}...{% endif %}`.
- Jira в этом режиме не изменяется.
            """
        )
    target_key_changelog = st.text_input("Release target", placeholder="MSP-8000", key="b2c_target")
    b2c_log_level = st.selectbox("Уровень логов", ["INFO", "DEBUG"], index=0, key="b2c_log")
    if st.button("Сгенерировать текст", key="b2c_run", use_container_width=True):
        if not target_key_changelog.strip():
            st.error("Укажи release target.")
        else:
            args = [
                sys.executable,
                str(MAIN_SCRIPT),
                "--release-target",
                target_key_changelog.strip(),
                "--mode",
                "changelog-preview",
                "--log-level",
                b2c_log_level,
            ]
            result = execute_command_ui(
                "B2: changelog-текст для документации",
                args,
                timeout_sec=3600,
                live_debug=(b2c_log_level == "DEBUG"),
            )
            if result.code == 0 and result.stdout.strip():
                parsed = extract_changelog_text(result.stdout, result.stderr).strip()
                if parsed:
                    st.session_state["b2c_text"] = parsed
                    st.session_state["b2c_editor"] = parsed
    b2c_text = st.session_state.get("b2c_text", "")
    if b2c_text:
        current_changelog = st.text_area(
            "Текст для вставки в исходный код документации (можно править перед копированием)",
            value=b2c_text,
            height=380,
            key="b2c_editor",
        )
        st.session_state["b2c_text"] = current_changelog
        clipboard_button("Скопировать текст", current_changelog, "b2c_text")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("B3. Одна релизная строка")
    with st.expander("Что делает", expanded=False):
        st.markdown(
            """
- Вход: ключ Jira-задачи.  
- Выход: краткое описание для релизной таблицы.
            """
        )
    issue_key = st.text_input("Ключ задачи", placeholder="MSP-1234", key="b1_issue")
    b1_log_debug = st.checkbox("DEBUG лог", key="b1_debug", value=False)
    if st.button("Сгенерировать", key="b1_run", use_container_width=True):
        if not issue_key.strip():
            st.error("Укажи ключ задачи.")
        else:
            args = [sys.executable, str(MAIN_SCRIPT), "--issue-short", issue_key.strip()]
            if b1_log_debug:
                args.extend(["--log-level", "DEBUG"])
            result = execute_command_ui(
                "B3: одна релизная строка",
                args,
                timeout_sec=3600,
                live_debug=b1_log_debug,
            )
            if result.code == 0 and result.stdout.strip():
                parsed = extract_issue_short_text(result.stdout, result.stderr).strip()
                if parsed:
                    st.session_state["b1_result_text"] = parsed
                    st.session_state["b1_out"] = parsed
    b1_text = st.session_state.get("b1_result_text", "")
    if b1_text:
        current = st.text_area("Результат", value=b1_text, height=100, key="b1_out")
        st.session_state["b1_result_text"] = current
        clipboard_button("Скопировать результат", current, "b1_result")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("B4. Preview релизной таблицы")
    with st.expander("Что делает", expanded=False):
        st.markdown(
            """
- Вход: ключ релизной задачи (`release parent`).  
- Выход: полная таблица в формате Jira wiki без записи в Jira.
            """
        )
    parent_key_preview = st.text_input("Release parent", placeholder="MSP-7000", key="b3_parent")
    b3_log_debug = st.checkbox("DEBUG лог", key="b3_debug", value=False)
    if st.button("Построить preview", key="b3_run", use_container_width=True):
        if not parent_key_preview.strip():
            st.error("Укажи release parent.")
        else:
            args = [sys.executable, str(MAIN_SCRIPT), "--release-parent", parent_key_preview.strip(), "--mode", "view"]
            if b3_log_debug:
                args.extend(["--log-level", "DEBUG"])
            result = execute_command_ui(
                "B4: preview релизной таблицы",
                args,
                timeout_sec=3600,
                live_debug=b3_log_debug,
            )
            if result.code == 0 and result.stdout.strip():
                st.session_state["b3_table_text"] = result.stdout.strip()
    b3_text = st.session_state.get("b3_table_text", "")
    if b3_text:
        current_table = st.text_area(
            "Таблица (можно править перед копированием)",
            value=b3_text,
            height=320,
            key="b3_table_editor",
        )
        st.session_state["b3_table_text"] = current_table
        clipboard_button("Скопировать таблицу", current_table, "b3_table")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("B5. Compare: эталон vs сгенерированное")
    with st.expander("Что делает и риски", expanded=False):
        st.markdown(
            """
Режим:
- берет таблицу из `release target`;
- дописывает `_Сгенерировано:_` в колонку `Краткое описание`;
- запускает LLM-судью;
- публикует отчет судьи комментарием в той же задаче.

Рекомендация:
- используйте копию эталонной таблицы, т.к. target изменяется.
            """
        )
    parent_key_compare = st.text_input("Release parent", placeholder="MSP-7000", key="b4_parent")
    target_key_compare = st.text_input("Release target", placeholder="MSP-8000", key="b4_target")
    compare_mode = st.selectbox("Режим compare", ["replace", "append"], index=0, key="b4_mode")
    skip_judge = st.checkbox("Не запускать LLM-судью (--skip-judge)", value=False, key="b4_skip")
    b4_log_level = st.selectbox("Уровень логов", ["INFO", "DEBUG"], index=1, key="b4_log")
    st.markdown(
        "<div class='warn'><b>Внимание:</b> таблица и комментарии в <code>release target</code> будут изменены.</div>",
        unsafe_allow_html=True,
    )
    if st.button("Запустить compare", key="b4_run", use_container_width=True):
        if not parent_key_compare.strip() or not target_key_compare.strip():
            st.error("Укажи release parent и release target.")
        else:
            args = [
                sys.executable,
                str(MAIN_SCRIPT),
                "--release-parent",
                parent_key_compare.strip(),
                "--release-target",
                target_key_compare.strip(),
                "--mode",
                "compare",
                "--compare-mode",
                compare_mode,
                "--log-level",
                b4_log_level,
            ]
            if skip_judge:
                args.append("--skip-judge")
            result = execute_command_ui(
                "B5: compare",
                args,
                timeout_sec=7200,
                live_debug=(b4_log_level == "DEBUG"),
            )
            merged_text = result.stdout + "\n" + result.stderr
            m = re.search(r"updated_rows=(\\d+)", merged_text)
            if m:
                st.info(f"Обновлено строк в таблице: {m.group(1)}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("B6. Проверка санитайзера")
    with st.expander("Что делает", expanded=False):
        st.markdown(
            """
- Вход: ключ Jira-задачи.  
- Выход: сравнение raw/sanitized для валидации очистки чувствительных данных.
            """
        )
    sanitizer_key = st.text_input("Ключ задачи", placeholder="MSP-8440", key="b6_issue")
    if st.button("Проверить санитайзер", key="b6_run", use_container_width=True):
        if not sanitizer_key.strip():
            st.error("Укажи ключ задачи.")
        else:
            args = [sys.executable, str(SANITIZER_SCRIPT), sanitizer_key.strip()]
            execute_command_ui(
                "B6: проверка санитайзера",
                args,
                timeout_sec=3600,
                live_debug=False,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def doc_qa_tools() -> None:
    st.markdown("<h3 class='block-title'>Doc QA: проверка на стоп-слова</h3>", unsafe_allow_html=True)
    st.markdown(
        "<p class='subtle'>Сканирует документацию по стартовой ссылке и показывает найденные стоп-слова.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    start_url = st.text_input("Стартовый URL", placeholder="https://docs.example.com/ru/", key="docqa_url")
    stop_words_path = st.text_input("Файл стоп-слов", value=str(STOPWORDS_DEFAULT), key="docqa_stopwords")
    c1, c2 = st.columns(2)
    with c1:
        delay = st.number_input(
            "Задержка между запросами (сек)",
            min_value=0.0,
            value=0.5,
            step=0.1,
            key="docqa_delay",
        )
    with c2:
        max_pages = st.number_input(
            "Лимит страниц (0 = без лимита)",
            min_value=0,
            value=0,
            step=10,
            key="docqa_max_pages",
        )

    if st.button("Запустить сканирование", key="docqa_run", use_container_width=True):
        if not start_url.strip():
            st.error("Укажи стартовый URL.")
        else:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
            tmp.close()
            args = [
                sys.executable,
                str(STOPWORDS_SCRIPT),
                "--url",
                start_url.strip(),
                "--stop-words",
                stop_words_path.strip(),
                "--delay",
                str(delay),
                "--output",
                tmp.name,
            ]
            if max_pages > 0:
                args.extend(["--max-pages", str(max_pages)])

            result = execute_command_ui(
                "Doc QA: сканирование стоп-слов",
                args,
                timeout_sec=7200,
                live_debug=False,
            )

            report_data: Dict[str, Any] = {}
            report_path = Path(tmp.name)
            if report_path.exists():
                try:
                    report_data = json.loads(report_path.read_text(encoding="utf-8"))
                except Exception:
                    report_data = {}

            if report_data:
                pages = report_data.get("pages", [])
                pages_with_hits = [p for p in pages if int(p.get("total_hits", 0)) > 0]
                m1, m2, m3 = st.columns(3)
                m1.metric("Страниц проверено", str(report_data.get("pages_checked", 0)))
                m2.metric("Всего вхождений", str(report_data.get("total_hits", 0)))
                m3.metric("Проблемных страниц", str(len(pages_with_hits)))

                if pages_with_hits:
                    st.markdown("#### Проблемные страницы")
                    rows = [
                        {"Статья": p.get("title", ""), "URL": p.get("url", ""), "Вхождений": p.get("total_hits", 0)}
                        for p in pages_with_hits
                    ]
                    st.dataframe(rows, use_container_width=True, hide_index=True)

                    with st.expander("Детали совпадений", expanded=False):
                        for page in pages_with_hits:
                            st.markdown(f"**{page.get('title', 'Без названия')}**")
                            st.caption(page.get("url", ""))
                            hits_map = page.get("hits", {})
                            for word, hits in hits_map.items():
                                st.markdown(f"- `{word}`: {len(hits)}")
                                for hit in hits[:3]:
                                    st.markdown(f"  - {hit.get('context', '')}")
                else:
                    st.success("Стоп-слова не найдены.")
            else:
                st.warning("JSON-отчет не распознан. Проверь stdout/stderr.")
    st.markdown("</div>", unsafe_allow_html=True)


def show_history() -> None:
    st.markdown("<h3 class='block-title'>История запусков</h3>", unsafe_allow_html=True)
    history = st.session_state.get("run_history", [])
    if not history:
        st.info("Запусков пока нет.")
        return
    rows = [
        {
            "Время": item.get("time", ""),
            "Действие": item.get("action", ""),
            "Код": item.get("code", ""),
            "Время, с": item.get("elapsed", ""),
        }
        for item in history
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def main() -> None:
    init_page()
    st.markdown("<h1 class='block-title'>Release Notes Studio</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtle'>Единый интерфейс для релизных заметок и Doc QA.</p>", unsafe_allow_html=True)

    tab_overview, tab_release, tab_docqa, tab_history = st.tabs(
        ["Обзор процесса", "Релизные заметки", "Проверка документации", "История запусков"]
    )

    with tab_overview:
        show_overview()
    with tab_release:
        release_notes_tools()
    with tab_docqa:
        doc_qa_tools()
    with tab_history:
        show_history()


if __name__ == "__main__":
    main()
