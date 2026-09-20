"""Projection helpers for a large effective deployment configuration.

Pure functions, no Django or request state. A merged ``get_deployment_config``
response for a real instance runs to hundreds of keys, which is more than a
model wants to pull into context to answer "what database is this pointed at".
These two shapings -- drill into one path, or list the keys without their
values -- are what make that config navigable in two cheap steps instead of one
expensive one. They live here rather than in the tool body so the GUI can adopt
the same projection later without a second implementation.
"""


class ConfigPathError(KeyError):
    """A path that does not resolve, carrying what *was* available at the miss.

    ``available`` is the list of keys (or, in a list, the valid index range) at
    the level that failed, so a caller can tell the user what to try instead of
    only that they were wrong.
    """

    def __init__(self, path: str, segment: str, available):
        self.path = path
        self.segment = segment
        self.available = available
        super().__init__(f"'{segment}' not found in configuration path '{path}'")


def project_config_path(config, path: str):
    """Follow a dotted ``path`` into ``config`` and return what is there.

    List elements are addressed by their index as a path segment, so
    ``dependencies.db.0.instance_name`` works the same way as a mapping key. An
    empty path returns ``config`` unchanged; anything unresolvable raises
    ``ConfigPathError``.
    """
    path = (path or "").strip().strip(".")
    if not path:
        return config

    current = config
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                raise ConfigPathError(path, segment, sorted(current.keys()))
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            try:
                index = int(segment)
                current = current[index]
            except (TypeError, ValueError, IndexError):
                raise ConfigPathError(
                    path, segment, [f"0..{len(current) - 1}" if current else "empty"]
                ) from None
        else:
            raise ConfigPathError(path, segment, [])
    return current


def config_key_outline(value):
    """The shape of ``value`` -- keys and types -- without any of the values.

    A mapping becomes ``{key: <type>}``, where a nested mapping reports its own
    key count and a list its length, so one call tells a caller which branch is
    worth drilling into. A non-mapping reports only its type, since there are no
    keys to outline.
    """
    if isinstance(value, dict):
        return {k: _describe(v) for k, v in sorted(value.items())}
    return {"_type": _describe(value)}


def _describe(value):
    if isinstance(value, dict):
        return f"object ({len(value)} keys)"
    if isinstance(value, (list, tuple)):
        return f"array ({len(value)} items)"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    return "string"
