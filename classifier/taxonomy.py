"""Taxonomy access: compact prompt catalog + tolerant id resolution.

The model never sees the raw 112 KB taxonomy JSON. It sees a compact catalog
(~17 KB, ~4k tokens) rendered once and reused verbatim as the system prompt so
the server's prefix cache can keep it warm.

The model is allowed to answer with a full dotted id, an alias, or a bare tag
name; resolve() maps all of those back to a canonical id, and anything that does
not match is reported as unresolved instead of being silently accepted.
"""

from __future__ import annotations

import json
from pathlib import Path


class Taxonomy:
    def __init__(self, doc: dict):
        self.doc = doc
        self.id: str = doc["id"]
        self.version: str = doc.get("version", "1.0")
        self.nodes: dict[str, dict] = {}
        self.parent: dict[str, str | None] = {}
        self.children: dict[str, list[str]] = {}
        self.level: dict[str, int] = {}
        self.alias: dict[str, str] = {}
        for root in doc["roots"]:
            self._walk(root, None)

    def _walk(self, node: dict, parent: str | None) -> None:
        nid = node["id"]
        self.nodes[nid] = node
        self.parent[nid] = parent
        self.children.setdefault(nid, [])
        self.level[nid] = int(node.get("level") or (nid.count(".") + 1))
        if parent:
            self.children.setdefault(parent, []).append(nid)
        for a in node.get("aliases") or []:
            self.alias.setdefault(a.strip().lower(), nid)
        self.alias.setdefault(self.label(node, "en").lower(), nid)
        for child in node.get("children") or []:
            self._walk(child, nid)

    @staticmethod
    def label(node: dict, lang: str = "en") -> str:
        return (node.get("label") or {}).get(lang) or node["id"]

    # ---------- prompt catalog ----------

    def catalog(self) -> str:
        """Compact one-line-per-node catalog, stable across calls (prefix cache)."""
        lines = [
            f"TAXONOMY {self.id} v{self.version}",
            "Levels: 1=domain (8 of them) | 2=topic (what to file the question under) | 3=tag (fine-grained type, multi-select).",
            "",
        ]
        for root in self.doc["roots"]:
            lines.append(f'[{root["id"]}] {self.label(root)} / {(root.get("label") or {}).get("zh", "")}'
                         + ("   (METHOD AXIS: techniques, combine with any knowledge domain)" if root.get("kind") == "method" else ""))
            for topic in root.get("children") or []:
                lines.append(f'  {topic["id"]}  {self.label(topic)} / {(topic.get("label") or {}).get("zh", "")}')
                tags = topic.get("children") or []
                if tags:
                    parts = [f'{t["id"].split(".", 2)[2]}:{self.label(t)}' for t in tags]
                    lines.append("    " + " | ".join(parts))
        return "\n".join(lines)

    # ---------- resolution ----------

    def resolve(self, raw: str, near: str | None = None) -> str | None:
        """Map a model answer onto a canonical node id (or None)."""
        if not raw or not isinstance(raw, str):
            return None
        key = raw.strip().strip("`\"'").lower()
        if key in self.nodes:
            return key
        key_no_space = key.replace(" ", "_").replace("-", "_")
        if key_no_space in self.nodes:
            return key_no_space
        if key in self.alias:
            return self.alias[key]
        if key_no_space in self.alias:
            return self.alias[key_no_space]
        # bare last segment, e.g. "prime_factorization" or "forbidden_points"
        hits = [nid for nid in self.nodes if nid.split(".")[-1] == key_no_space]
        if near:
            scoped = [nid for nid in hits if nid.startswith(near + ".")]
            if len(scoped) == 1:
                return scoped[0]
        if len(hits) == 1:
            return hits[0]
        # prefix-ish match on the label
        if len(hits) > 1:
            for nid in hits:
                if self.label(self.nodes[nid]).lower() == raw.strip().lower():
                    return nid
        return None

    def domain_of(self, nid: str) -> str:
        cur = nid
        while self.parent.get(cur):
            cur = self.parent[cur]
        return cur

    def is_leaf(self, nid: str) -> bool:
        return not self.children.get(nid)

    def name(self, nid: str) -> str:
        return self.label(self.nodes[nid]) if nid in self.nodes else nid

    def check_ids(self, ids: list[str]) -> list[str]:
        return [i for i in ids if i not in self.nodes]


def load(path: str | Path) -> Taxonomy:
    return Taxonomy(json.loads(Path(path).read_text(encoding="utf-8")))
