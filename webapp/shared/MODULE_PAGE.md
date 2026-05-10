# AutoLab module UI (agent contract)

Autonomous agents that add a **dashboard page** (Flask + Jinja) **must** follow this contract so every module looks and behaves like the rest of the app.

## Source of truth

| Asset | Path |
|--------|------|
| Jinja base | `webapp/templates/module_layout.html` |
| Shared shell CSS | `webapp/shared/static/module_shell.css` (loaded by the base; do not skip) |
| Global reset / body | `webapp/shared/static/base.css` (loaded by the base) |
| This spec | `webapp/shared/MODULE_PAGE.md` |

## Do / don’t

- **Do** `{% extends "module_layout.html" %}` as the first line of every module template.
- **Do** add a `template_folder="templates"` (and usually `static_folder="static"`) on the module `Blueprint`, register the blueprint in `webapp/__init__.py` `create_app()`, and add the module to `app/runtime/modules.py` if it is toggleable.
- **Do** put page-specific styles in `webapp/modules/<name>/static/<name>.css` and link it in `{% block head_extra %}` with `url_for('<blueprint>.static', filename='...', v=asset_version)`.
- **Don’t** hand-roll a second `<!DOCTYPE html>`, `<head>`, or outer `app-shell` layout. Use the base; override `shell_inner` only for rare full-page custom layouts (see below).
- **Don’t** link only `base.css` and skip `module_shell.css` — the base already includes both.

## Required Jinja blocks (default pattern)

Override at minimum:

1. **`module_title`** — short name in `<title> … · AutoLab` (e.g. `Wallapop`).
2. **`module_heading`** — uppercase-styled sidebar title (usually the same label as `module_title`).
3. **`content`** — main column body. Rendered inside `<div class="container module-container">` after the back link.

## Optional blocks

| Block | Use |
|--------|-----|
| `doc_title` | Full `<title>` if the default `module_title · AutoLab` is wrong. |
| `sidebar_lead` | Intro under the heading; wrap text in `<p class="sidebar-lead">…</p>`. |
| `sidebar_nav` | In-page anchors: `<a class="side-link" href="#section-id">…</a>`. |
| `head_extra` | Module CSS/JS after shared CSS (charts, extra stylesheet). |
| `body_scripts` | Scripts at end of `<body>`. |
| `body_prefix` | Rare markup before the shell (e.g. notification bar). |
| `body_class` | Extra classes on `<body>` for scoped CSS. |
| `shell_extra_class` | Extra classes on `.app-shell` (leading space in block: ` se-shell`). |
| `sidebar` | Replace the entire sidebar column (custom controls). |
| `main_content` | Replace everything in `.main` **after** the standard “← AutoLab” nav — use for full-width pages **without** the default `.container` (hardware monitor). |
| `shell_inner` | Replace sidebar **and** main columns entirely (StreamElements). Prefer not to use for new modules. |

## Minimal example

`webapp/modules/example/templates/example.html`:

```jinja
{% extends "module_layout.html" %}
{% block module_title %}Example{% endblock %}
{% block module_heading %}Example{% endblock %}
{% block head_extra %}
  <link rel="stylesheet" href="{{ url_for('example.static', filename='example.css', v=asset_version) }}">
{% endblock %}
{% block sidebar_lead %}
  <p class="sidebar-lead">One sentence describing this screen.</p>
{% endblock %}
{% block sidebar_nav %}
  <a class="side-link" href="#main">Main</a>
{% endblock %}
{% block content %}
  <h1>Example</h1>
  <p class="subtitle">Supporting text.</p>
  <section id="main">…</section>
{% endblock %}
```

`webapp/modules/example/__init__.py` (sketch):

```python
example_bp = Blueprint(
    "example", __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/example",
)
```

## Tables and empty states

- Prefer `<table class="module-table">` for generic data tables (styles ship with `module_shell.css`).
- Use a module-specific class when you need distinct styling (e.g. `table class="terms module-table"`).

## Related registry docs

- Flask wiring: docstring in `webapp/__init__.py`.
- Compose toggles and home cards: `app/runtime/modules.py`.
