def index_for(dir_path: str, concepts: list[tuple[str, str]], subdirs: list[str]) -> str:
    parts = [f"# {dir_path if dir_path else 'Bundle root'}"]
    if concepts:
        parts.append("")
        parts.append("## Concepts")
        for name, description in sorted(concepts):
            stem = name.removesuffix(".md")
            entry = f"- [{stem}]({name})"
            if description:
                entry += f" - {description}"
            parts.append(entry)
    if subdirs:
        parts.append("")
        parts.append("## Subdirectories")
        for subdir in sorted(subdirs):
            parts.append(f"- [{subdir}]({subdir}/)")
    return "\n".join(parts) + "\n"