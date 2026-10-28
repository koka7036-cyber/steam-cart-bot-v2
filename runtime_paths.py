"""Portable runtime path resolution for the Windows bot and its tests."""
from pathlib import Path
from typing import Optional, Tuple, Union

PathLike = Union[str, Path]


def resolve_runtime_paths(
    script_file: PathLike,
    configured_data_dir: Optional[PathLike] = None,
) -> Tuple[Path, Path]:
    """Return (script directory, data directory), independent of current working directory.

    If no data directory is configured, runtime data stays beside the script so moving
    the complete bot folder preserves the database and session files.
    """
    base_dir = Path(script_file).expanduser().resolve().parent
    if configured_data_dir:
        data_dir = Path(configured_data_dir).expanduser().resolve()
    else:
        data_dir = base_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return base_dir, data_dir
