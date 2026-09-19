RESERVED = {"index.md", "log.md"}


class GCSBundleStore:
    def __init__(self, bucket: str, prefix: str = "") -> None:
        from google.cloud import storage

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)
        self._prefix = prefix.strip("/")

    def _key(self, rel_path: str) -> str:
        return f"{self._prefix}/{rel_path}" if self._prefix else rel_path

    def list_markdown(self, rel_dir: str = "") -> list[str]:
        prefix = self._key(rel_dir).rstrip("/") + "/" if rel_dir else self._key("") + "/"
        names = []
        for blob in self._bucket.list_blobs(prefix=prefix, delimiter="/"):
            if blob.name.endswith(".md") and blob.name.split("/")[-1] not in RESERVED:
                names.append(blob.name.rsplit("/", 1)[-1])
        return sorted(names)

    def list_subdirs(self, rel_dir: str = "") -> list[str]:
        prefix = self._key(rel_dir).rstrip("/") + "/" if rel_dir else self._key("") + "/"
        iterator = self._bucket.list_blobs(prefix=prefix, delimiter="/")
        for _ in iterator:
            pass
        names = []
        for prefix_str in iterator.prefixes:
            name = prefix_str[len(prefix) :].rstrip("/")
            if name:
                names.append(name)
        return sorted(names)

    def read_text(self, rel_path: str) -> str:
        blob = self._bucket.blob(self._key(rel_path))
        return blob.download_as_text()

    def write_text(self, rel_dir: str, filename: str, content: str) -> None:
        key = self._key(f"{rel_dir}/{filename}" if rel_dir else filename)
        self._bucket.blob(key).upload_from_string(content, content_type="text/markdown")

    def walk(self, rel_dir: str = "") -> list[str]:
        prefix = self._key(rel_dir).rstrip("/") + "/" if rel_dir else self._key("") + "/"
        paths = []
        for blob in self._bucket.list_blobs(prefix=prefix, delimiter=None):
            name = blob.name
            if not name.startswith(prefix):
                continue
            rel = name[len(prefix) :]
            if rel:
                paths.append(rel)
        return sorted(paths)

    def exists(self, rel_path: str) -> bool:
        return self._bucket.blob(self._key(rel_path)).exists()