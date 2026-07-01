from __future__ import annotations

from pathlib import Path

COGS_PACKAGE = "src.cogs"


def get_cogs_dir() -> Path:
    """Return the path to the cogs package directory."""
    return Path(__file__).resolve().parent.parent / "cogs"


def discover_cog_extensions(cogs_dir: Path | None = None, package: str = COGS_PACKAGE) -> list[str]:
    """Return import paths for each cog package under cogs_dir."""
    root = cogs_dir or get_cogs_dir()
    extensions: list[str] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        if not (path / "__init__.py").is_file():
            continue
        extensions.append(f"{package}.{path.name}")
    return extensions


def resolve_cog_extension(name: str, *, package: str = COGS_PACKAGE, cogs_dir: Path | None = None) -> str:
    """Resolve a short or full cog name to a loadable extension path."""
    extensions = discover_cog_extensions(cogs_dir, package)
    if name in extensions:
        return name

    short_name = name.removeprefix(f"{package}.").removeprefix("cogs.")
    extension = f"{package}.{short_name}"
    if extension in extensions:
        return extension

    available = ", ".join(ext.removeprefix(f"{package}.") for ext in extensions)
    msg = f"Unknown cog `{name}`. Available: {available}"
    raise ValueError(msg)
