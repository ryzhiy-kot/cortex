import json
import re
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError

from cortex.bundle.local import RESERVED
from cortex.bundle.parser import ParsedConcept, ParseError, parse_concept
from cortex.models import PrepareError, PrepareJob, PrepareStatus
from cortex.prepare.llm import LLMProvider
from cortex.telemetry import logger, tracer

SAFE_BUNDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ReviewDecision(BaseModel):
    action: Literal["create", "consolidate"]
    into: str | None = None
    reason: str


class ReviewPlan(BaseModel):
    bundle: str | None = None
    decisions: dict[str, ReviewDecision] = {}


def _is_text(path: Path) -> bool:
    """Whether a file's content is text (UTF-8, optional BOM).

    Source material may be any text format — prepare is what turns it into OKF.
    A filename extension is not consulted, so `.csv`, `.html`, markdown without
    frontmatter, and extension-less files all qualify; binary files don't.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


class ReviewPlanError(ValueError):
    pass


class PrepareFailure(Exception):
    def __init__(self, item: str, reason: str) -> None:
        super().__init__(f"{item}: {reason}")
        self.item = item
        self.reason = reason


@dataclass
class PendingWrite:
    parsed: ParsedConcept
    action: str
    into: str | None
    additions: list[str]
    create_rel: str = ""


def _load_spec() -> str:
    here = Path(__file__).resolve()
    candidates = [here.parent / "SPEC.md"]
    candidates += [here.parents[i] / "lib" / "okf" / "SPEC.md" for i in range(3, 6)]
    candidates.append(Path.cwd() / "lib" / "okf" / "SPEC.md")
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:markdown|md|text)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _render_concept(frontmatter: dict, body: str) -> str:
    header = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{header}\n---\n\n{body}\n" if body else f"---\n{header}\n---\n"


def _safe_member(target_root: Path, member: str) -> Path:
    target = (target_root / member).resolve()
    if not str(target).startswith(str(target_root.resolve())):
        raise PrepareFailure(member, "zip member escapes staging directory")
    return target


def _extract_zip(zip_path: Path, staging: Path) -> None:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                target = _safe_member(staging, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
    except zipfile.BadZipFile as exc:
        raise PrepareFailure(
            zip_path.name, f"not a readable zip archive: {exc}"
        ) from exc


def _staged_files(staging: Path) -> list[str]:
    root = staging.resolve()
    return [
        str(path.relative_to(root))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _source_label(job: PrepareJob, source_name: str) -> str:
    return f"{job.source}:{source_name}" if job.source != source_name else source_name


class PrepareRunner:
    def __init__(
        self,
        llm: LLMProvider,
        bundles_root: Path,
        staging_root: Path,
        manifest_factory: Callable[[], list[dict]],
    ) -> None:
        self._llm = llm
        self._bundles_root = bundles_root
        self._staging_root = staging_root
        self._manifest_factory = manifest_factory
        self._spec = _load_spec()

    def run(
        self, job: PrepareJob, payload: bytes, filename: str, forced_bundle: str | None
    ) -> None:
        filename = Path(filename).name
        job.source = filename
        staging = self._staging_root / job.job_id
        try:
            staging.mkdir(parents=True, exist_ok=True)
            if filename.lower().endswith(".zip"):
                zip_path = staging / filename
                zip_path.write_bytes(payload)
                content_root = staging / "unpacked"
                content_root.mkdir(parents=True, exist_ok=True)
                _extract_zip(zip_path, content_root)
            else:
                (staging / filename).write_bytes(payload)
                content_root = staging

            plan = self._review(job, content_root, forced_bundle)
            if plan.decisions:
                self._author(job, content_root, plan)
            job.target_bundle = plan.bundle
            job.status = PrepareStatus.DONE
        except PrepareFailure as exc:
            job.status = PrepareStatus.FAILED
            job.errors = [PrepareError(item=exc.item, reason=exc.reason)]
        except Exception as exc:  # noqa: BLE001 - job failure is reported, not raised
            job.status = PrepareStatus.FAILED
            job.errors = [PrepareError(item=filename, reason=str(exc))]
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _review(
        self, job: PrepareJob, content_root: Path, forced_bundle: str | None
    ) -> dict:
        job.status = PrepareStatus.REVIEWING
        manifest = self._manifest_factory()
        files = _staged_files(content_root)
        supported = [f for f in files if _is_text(content_root / f)]
        job.skipped_files = [f for f in files if f not in supported]
        if not supported:
            return ReviewPlan(bundle=forced_bundle, decisions={})

        with tracer().start_as_current_span("prepare.review") as span:
            span.set_attribute("cortex.files", len(supported))
            span.set_attribute("cortex.bundles", len(manifest))
            prompt = {
                "task": "REVIEW",
                "forced_bundle": forced_bundle,
                "files": supported,
                "bundles": manifest,
            }
            try:
                response = self._llm.complete(
                    system=_REVIEW_SYSTEM.format(spec=self._spec),
                    user=json.dumps(prompt, indent=2),
                    output_type=ReviewPlan,
                )
            except ValidationError as exc:
                raise ReviewPlanError(
                    f"LLM returned an invalid review plan: {exc.errors()[0]['msg']}"
                ) from exc
            plan = self._validate_plan(response, forced_bundle, supported, manifest)
            span.set_attribute("cortex.decisions", len(plan.decisions))
            span.set_attribute("cortex.bundle", plan.bundle or "")
            return plan

    def _validate_plan(
        self,
        plan: ReviewPlan,
        forced_bundle: str | None,
        supported: list[str],
        manifest: list[dict],
    ) -> ReviewPlan:
        existing = {item["concept_path"] for item in manifest}
        bundle = forced_bundle if forced_bundle is not None else plan.bundle
        if bundle is None or SAFE_BUNDLE_RE.match(bundle) is None:
            raise ReviewPlanError(
                f"LLM did not choose a valid bundle name (got: {bundle!r})"
            )
        allowed = set(supported)
        decisions: dict[str, ReviewDecision] = {}
        for source_name, decision in plan.decisions.items():
            if source_name not in allowed:
                raise ReviewPlanError(
                    f"review names unknown source file: {source_name}"
                )
            if decision.action == "consolidate":
                into = (decision.into or "").strip().removesuffix(".md")
                if not into or into not in existing:
                    raise ReviewPlanError(
                        f"decision for {source_name} consolidates into unknown concept: {decision.into}"
                    )
                decisions[source_name] = decision.model_copy(update={"into": into})
            else:
                decisions[source_name] = decision
            allowed.discard(source_name)
        if allowed:
            raise ReviewPlanError(f"review omitted decisions for: {sorted(allowed)}")
        return plan.model_copy(update={"bundle": bundle, "decisions": decisions})

    def _author(self, job: PrepareJob, content_root: Path, plan: ReviewPlan) -> None:
        job.status = PrepareStatus.AUTHORING
        bundle = plan.bundle
        pending: list[PendingWrite] = []
        for source_name, decision in plan.decisions.items():
            content = (content_root / source_name).read_text(
                encoding="utf-8-sig", errors="replace"
            )
            existing = (
                self._read_existing(decision.into)
                if decision.action == "consolidate"
                else None
            )
            with tracer().start_as_current_span("prepare.author") as span:
                span.set_attribute("cortex.source", source_name)
                span.set_attribute("cortex.action", decision.action)
                span.set_attribute("cortex.into", decision.into or "")
                prompt = {
                    "task": "AUTHOR",
                    "source": source_name,
                    "content": content,
                    "decision": decision.model_dump(),
                    "existing_concept": existing,
                }
                response = self._llm.complete(
                    system=_AUTHOR_SYSTEM.format(spec=self._spec),
                    user=json.dumps(prompt, indent=2),
                )
                raw = _strip_markdown_fence(str(response))
                try:
                    parsed = parse_concept(raw, source_name)
                except ParseError as exc:
                    raise PrepareFailure(
                        source_name, f"LLM authored invalid OKF: {exc}"
                    ) from exc
            label = _source_label(job, source_name)
            if decision.action == "consolidate":
                existing_sources = self._existing_sources(existing)
                additions = (
                    existing_sources + [label]
                    if label not in existing_sources
                    else existing_sources
                )
            else:
                additions = [label]
            pending.append(
                PendingWrite(
                    parsed=parsed,
                    action=decision.action,
                    into=decision.into,
                    additions=additions,
                    create_rel=Path(source_name).with_suffix("").as_posix(),
                )
            )
        self._persist(job, bundle, pending)

    @staticmethod
    def _existing_sources(existing: dict | None) -> list[str]:
        if existing is None:
            return []
        raw = existing.get("frontmatter", {}).get("sources", [])
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw]

    def _read_existing(self, concept_path: str) -> dict | None:
        bundle, _, rel = concept_path.partition("/")
        try:
            text = (self._bundles_root / bundle / f"{rel}.md").read_text(
                encoding="utf-8"
            )
        except (FileNotFoundError, NotADirectoryError):
            return None
        try:
            parsed = parse_concept(text, concept_path)
        except ParseError:
            return None
        return {"frontmatter": parsed.frontmatter, "body": parsed.body}

    def _persist(self, job: PrepareJob, bundle: str, pending: list[PendingWrite]) -> None:
        with tracer().start_as_current_span("prepare.persist") as span:
            span.set_attribute("cortex.writes", len(pending))
            try:
                self._persist_impl(job, bundle, pending)
            except Exception:
                logger.error(
                    "prepare persist failed for job %s", job.job_id, exc_info=True
                )
                raise
            finally:
                span.set_attribute("cortex.created", len(job.created_concepts))
                span.set_attribute("cortex.updated", len(job.updated_concepts))

    def _persist_impl(
        self, job: PrepareJob, bundle: str, pending: list[PendingWrite]
    ) -> None:
        root = self._bundles_root.resolve()
        planned: list[tuple[Path, str, PendingWrite]] = []
        for write in pending:
            if write.action == "consolidate":
                into_bundle, _, into_rel = write.into.partition("/")
                target = (root / into_bundle / f"{into_rel}.md").resolve()
                if not str(target).startswith(str(root)):
                    raise PrepareFailure(
                        write.into, "consolidation target escapes bundles root"
                    )
            else:
                rel = write.create_rel
                if f"{rel}.md".split("/")[-1] in RESERVED:
                    raise PrepareFailure(
                        write.parsed.path,
                        "concept name collides with a reserved OKF file",
                    )
                bundle_root = (root / bundle).resolve()
                if not str(bundle_root).startswith(str(root)):
                    raise PrepareFailure(bundle, "bundle name escapes bundles root")
                target = (bundle_root / f"{rel}.md").resolve()
                if not str(target).startswith(str(bundle_root)):
                    raise PrepareFailure(
                        write.parsed.path, "concept path escapes target bundle"
                    )
            frontmatter = dict(write.parsed.frontmatter)
            frontmatter["sources"] = write.additions
            planned.append(
                (target, _render_concept(frontmatter, write.parsed.body), write)
            )

        backups: dict[Path, bytes | None] = {}
        created_dirs: list[Path] = []
        try:
            for target, content, write in planned:
                backups[target] = target.read_bytes() if target.exists() else None
                parent = target.parent
                new_dirs = []
                probe = parent
                while not probe.exists() and probe != root:
                    new_dirs.append(probe)
                    probe = probe.parent
                for new_dir in reversed(new_dirs):
                    new_dir.mkdir(exist_ok=True)
                    created_dirs.append(new_dir)
                target.write_text(content, encoding="utf-8")
                if write.action == "consolidate":
                    job.updated_concepts.append(write.into)
                else:
                    job.created_concepts.append(f"{bundle}/{write.create_rel}")
        except Exception as exc:
            for target, original in backups.items():
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(original)
            for new_dir in sorted(
                created_dirs, key=lambda path: len(path.parts), reverse=True
            ):
                try:
                    new_dir.rmdir()
                except OSError:
                    pass
            raise PrepareFailure(
                job.source, f"failed to write prepared concepts: {exc}"
            ) from exc


_REVIEW_SYSTEM = """You are the authoring utility inside Cortex, a knowledge service built on this specification:

{spec}

Given source material that is NOT yet OKF, decide per source file whether its knowledge already
exists among the current bundles.

You respond in structured form (enforced by the host; you must not add prose):
- "bundle": the bundle the new concepts should live in; reuse an existing bundle name when
  suitable, otherwise a new concise name.
- "decisions": one entry per source file, with:
  - "action": "create" for distinct new knowledge, or "consolidate" when the file's knowledge
    duplicates or extends a concept that already exists.
  - "into": required only for "consolidate" — the bundle-qualified concept path it merges into.
  - "reason": one short sentence justifying the choice.

Every source file listed in the prompt must appear in "decisions".
"""

_AUTHOR_SYSTEM = """You are the authoring utility inside Cortex, a knowledge service built on this specification:

{spec}

Produce ONE concept file in valid OKF: markdown with YAML frontmatter. Frontmatter MUST include:
- "type": a short, self-explanatory value (e.g. reference, guide, playbook)
- "title": concise title
- "description": one-sentence summary

Then a markdown body. If "existing_concept" is provided, merge the new content into it and return
the full merged concept; do not drop the existing body. Do not include a "sources" field.
Return ONLY the concept file content, no explanations.
"""
