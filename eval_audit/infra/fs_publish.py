"""Filesystem-publishing helpers.

Post-history-retirement (2026-04-28) and the follow-on simplification
(2026-04-28b) the publishing model is intentionally tiny:

* Callers write the canonical artifact directly to its visible path
  (``<root>/<stem>.latest.<ext>``); no stamped intermediate is created.
  Crash safety is handled by :func:`write_text_atomic` /
  :func:`write_bytes_atomic`, which use ``safer.open`` to write to a temp
  file and ``os.replace`` it onto the target on successful close.
* :func:`link_alias` creates cross-tree navigation symlinks (e.g.
  ``summary_root/level_001.latest -> summary_root/level_001/``). It is
  the only "alias" concept that remains; there is no longer a
  same-directory rename branch because there is no longer a stamped
  intermediate to rename.
* The functions ``stamped_history_dir``, ``history_publish_root``, and
  ``write_latest_alias`` were removed in this pass. ``stamp`` strings are
  still useful as JSON-content metadata (``generated_utc``); callers that
  need them compute one inline.
"""
from __future__ import annotations

import os
from pathlib import Path

import safer
from loguru import logger

from eval_audit.infra.logging import rich_link


def safe_unlink(path: Path) -> None:
    if path.exists() or path.is_symlink():
        path.unlink()


def symlink_to(target: str | os.PathLike[str], link_path: Path) -> Path:
    """Create or replace a symlink at ``link_path`` pointing at ``target``.
    The parent of ``link_path`` is created if missing. The link is relative
    so trees can be moved together without breaking it."""
    target = Path(target).expanduser().resolve()
    link_path.parent.mkdir(parents=True, exist_ok=True)
    safe_unlink(link_path)
    rel_src = os.path.relpath(target, start=link_path.parent)
    os.symlink(rel_src, link_path)
    logger.debug(f'Write link 🔗: {rich_link(link_path)}')
    return link_path


def link_alias(src: Path, alias_root: Path, alias_name: str) -> Path:
    """Create a navigation symlink ``alias_root/alias_name -> src``.

    Used for cross-tree aliases like
    ``summary_root/README.latest.txt -> level_001/README.latest.txt`` and
    ``summary_root/level_001.latest -> summary_root/level_001/`` — cases
    where the canonical artifact lives at a different path and we want a
    stable navigation entry point. For the canonical artifact itself,
    write directly to its target via :func:`write_text_atomic` /
    :func:`write_bytes_atomic`; no alias step is required.
    """
    alias_fpath = alias_root / alias_name
    if src == alias_fpath:
        return alias_fpath
    safe_unlink(alias_fpath)
    rel_src = os.path.relpath(src, start=alias_fpath.parent)
    os.symlink(rel_src, alias_fpath)
    logger.debug(f'Write link 🔗: {rich_link(alias_fpath)}')
    return alias_fpath


def write_text_atomic(fpath: Path, text: str, *, encoding: str = 'utf-8') -> Path:
    """Write ``text`` to ``fpath`` atomically.

    Uses ``safer.open`` to write to a temp file and ``os.replace`` it onto
    the target on successful close. A crash mid-write leaves the target
    untouched (the previous content survives, or the path stays absent if
    it didn't exist before). Creates parent directories if missing.
    """
    with safer.open(fpath, 'w', make_parents=True, encoding=encoding) as fp:
        fp.write(text)
    return Path(fpath)


def write_bytes_atomic(fpath: Path, data: bytes) -> Path:
    """Binary equivalent of :func:`write_text_atomic`."""
    with safer.open(fpath, 'wb', make_parents=True) as fp:
        fp.write(data)
    return Path(fpath)
