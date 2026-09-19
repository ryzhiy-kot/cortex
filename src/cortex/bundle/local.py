from pathlib import Path

RESERVED = {"index.md", "log.md"}


class LocalBundleStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _resolve(self, rel_path: str) -> Path:
        path = (self._root / rel_path).resolve()
        if not str(path).startswith(str(self._root)):
            raise ValueError(f"path escapes bundle root: {rel_path}")
        return path

    def list_markdown(self, rel_dir: str = "") -> list[str]:
        directory = self._resolve(rel_dir)
        names = []
        for child in sorted(directory.iterdir()):
            if child.is_file() and child.suffix == ".md" and child.name not in RESERVED:
                names.append(child.name)
        return names

    def list_subdirs(self, rel_dir: str = "") -> list[str]:
        directory = self._resolve(rel_dir)
        return sorted(child.name for child in directory.iterdir() if child.is_dir())

    def read_text(self, rel_path: str) -> str:
        return self._resolve(rel_path).read_text(encoding="utf-8")

    def write_text(self, rel_dir: str, filename: str, content: str) -> None:
        target = self._resolve(rel_dir) / filename
        target.write_text(content, encoding="utf-8")

    def walk(self, rel_dir: str = "") -> list[str]:
        root_dir = self._resolve(rel_dir)
        paths = []
        for child in sorted(root_dir.rglob("*")):
            if child.is_file():
                paths.append(str(child.relative_to(self._root)))
        return paths

    def exists(self, rel_path: str) -> bool:
        return self._resolve(rel_path).exists()