"""Custom template tags and filters for deployment GUI."""
import json

from django import template

register = template.Library()


@register.filter
def jsonify(value):
    """Serialize a value to a JSON string for safe inline embedding.

    Usage in a data attribute:
        <div data-payload='{{ obj|jsonify }}' @click="JSON.parse($el.dataset.payload)">
    """
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return "{}"


@register.filter
def get_item(dictionary, key):
    """Look up a dictionary value by variable key.

    Usage: {{ my_dict|get_item:my_var }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


# Environment color mappings for well-known environment types.
# Unknown environments get a neutral blue.
_ENV_BORDER_COLORS = {
    "prod": "border-red-500",
    "production": "border-red-500",
    "test": "border-yellow-500",
    "testing": "border-yellow-500",
    "staging": "border-yellow-500",
    "stage": "border-yellow-500",
    "dev": "border-green-500",
    "development": "border-green-500",
}

_ENV_DOT_COLORS = {
    "prod": "bg-red-500",
    "production": "bg-red-500",
    "test": "bg-yellow-500",
    "testing": "bg-yellow-500",
    "staging": "bg-yellow-500",
    "stage": "bg-yellow-500",
    "dev": "bg-green-500",
    "development": "bg-green-500",
}

_ENV_LABELS = {
    "prod": "Production",
    "production": "Production",
    "test": "Testing",
    "testing": "Testing",
    "staging": "Staging",
    "stage": "Staging",
    "dev": "Development",
    "development": "Development",
}


@register.filter
def env_border_color(env_name):
    """Return Tailwind border color class for an environment.

    Usage: {{ env|env_border_color }}
    """
    return _ENV_BORDER_COLORS.get(env_name, "border-blue-500")


@register.filter
def env_dot_color(env_name):
    """Return Tailwind background color class for an environment dot indicator.

    Usage: {{ env|env_dot_color }}
    """
    return _ENV_DOT_COLORS.get(env_name, "bg-blue-500")


@register.filter
def env_label(env_name):
    """Return human-readable label for an environment.

    Usage: {{ env|env_label }}
    """
    return _ENV_LABELS.get(env_name, env_name.capitalize() if env_name else "")


@register.filter
def dep_display(value):
    """Render a dependency role target — a single instance name or a list.

    Usage: {{ target|dep_display }}
    """
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value


@register.filter
def value_kind(value):
    """Classify a config value for the recursive config_value.html partial.

    Usage: {% if value|value_kind == "dict" %}...
    """
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, (list, tuple)):
        return "list"
    return "scalar"


# dependency wiring-kind badge styling, shared by the instance detail panel's
# Dependencies box and the DAG legend/ports so the same concept looks the same
# everywhere: resource (NERD0004, authoritative) / repo_class (legacy
# repo_class_name) / instance (present on the edge but undeclared -- a raw,
# direct pointer; reuses the amber already used for "stale" in the dependency
# picker).
_KIND_BADGES = {
    "resource": {
        "letter": "R",
        "label": "Resource",
        "classes": "bg-indigo-50 text-indigo-700 border-indigo-300",
    },
    "repo_class": {
        "letter": "C",
        "label": "Repo Class",
        "classes": "bg-slate-100 text-slate-700 border-slate-300",
    },
    "instance": {
        "letter": "I",
        "label": "Direct",
        "classes": "bg-amber-50 text-amber-700 border-amber-300",
    },
}


@register.filter
def kind_badge(kind):
    """Look up the badge display info (letter/label/Tailwind classes) for a
    dependency wiring kind. Usage: {% with badge=row.kind|kind_badge %}
    """
    return _KIND_BADGES.get(kind, _KIND_BADGES["instance"])


@register.simple_tag
def kind_badges():
    """All wiring-kind badges (resource/repo_class/instance), for the DAG legend.

    Usage: {% kind_badges as badges %}{% for kind, badge in badges.items %}...
    """
    return _KIND_BADGES


# BACON discovery capability kinds (hmd-docs-bacon schema.rst), one colour
# each so a capability search result reads at a glance. Kept distinct from
# _KIND_BADGES above, which is about dependency *wiring*, not capabilities.
_CAPABILITY_KIND_CLASSES = {
    "endpoint": "bg-indigo-50 text-indigo-700 border-indigo-300",
    "cli_command": "bg-emerald-50 text-emerald-700 border-emerald-300",
    "function": "bg-sky-50 text-sky-700 border-sky-300",
    "class": "bg-violet-50 text-violet-700 border-violet-300",
    "operation": "bg-amber-50 text-amber-700 border-amber-300",
}


@register.filter
def capability_kind_badge(kind):
    """Tailwind classes for a BACON capability ``kind`` badge; a neutral grey
    for anything outside the enum. Usage: {{ cap.kind|capability_kind_badge }}
    """
    return _CAPABILITY_KIND_CLASSES.get(
        kind, "bg-gray-100 text-gray-700 border-gray-300"
    )
