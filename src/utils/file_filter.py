def should_skip_file(filename: str) -> bool:
    skip_patterns = [".lock", ".min.", "package-lock.json", ".svg", ".png"]
    return any(pattern in filename for pattern in skip_patterns)


def filter_files(files: list) -> list:
    return [f for f in files if not should_skip_file(f.get("filename", ""))]
