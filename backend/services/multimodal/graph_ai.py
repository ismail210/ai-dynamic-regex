"""Lightweight GraphSAGE training and structural-graph inference."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from config import settings


NODE_KINDS = (
    "steel_section",
    "beam",
    "column",
    "brace",
    "plate",
    "bolt",
    "weld",
    "connection",
    "dimension",
    "symbol",
    "label",
    "geometry",
    "text",
    "other",
)
ROLE_LABELS = ("beam", "column", "brace", "plate", "connection", "other")
GRAPH_EMBEDDING_DIM = 48
EDGE_RELATIONS = (
    "connected_to",
    "nearest",
    "nearest_geometry",
    "nearest_label",
    "supports",
    "inside",
    "left_of",
    "right_of",
    "above",
    "below",
    "parallel",
    "perpendicular",
    "distance",
    "reference",
    "intersects",
    "adjacent",
    "touches",
    "same_tag",
    "other",
)
# The relation vocabulary is positional in the trained edge-gate weights, so
# growing EDGE_RELATIONS changes the edge-attribute width and stops older
# checkpoints from loading. Checkpoints now record their own vocabulary;
# these entries recover it for ones saved before that, keyed by relation
# count. Add a new entry here whenever EDGE_RELATIONS grows.
_LEGACY_EDGE_RELATIONS = {
    18: tuple(name for name in EDGE_RELATIONS if name != "same_tag"),
}
_LOCK = threading.RLock()
_RUNTIME: Optional[tuple[Any, Any, Dict[str, Any]]] = None


def _torch():
    from services.multimodal.torch_runtime import load_torch

    return load_torch()


class _GraphSAGEModel:
    """Thin wrapper that builds a torch module without importing torch eagerly."""

    @staticmethod
    def create(
        input_dim: int,
        hidden_dim: int,
        role_count: int,
        relation_count: int = len(EDGE_RELATIONS),
    ):
        torch = _torch()

        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.self_1 = torch.nn.Linear(input_dim, hidden_dim)
                self.neighbor_1 = torch.nn.Linear(input_dim, hidden_dim)
                self.self_2 = torch.nn.Linear(hidden_dim, hidden_dim)
                self.neighbor_2 = torch.nn.Linear(hidden_dim, hidden_dim)
                self.role_head = torch.nn.Linear(hidden_dim, role_count)
                self.consistency_head = torch.nn.Linear(hidden_dim, 1)
                self.missing_head = torch.nn.Linear(hidden_dim, 1)
                self.incorrect_head = torch.nn.Linear(hidden_dim, 1)
                self.edge_gate_1 = torch.nn.Linear(relation_count + 2, 1)
                self.edge_gate_2 = torch.nn.Linear(relation_count + 2, 1)

            @staticmethod
            def aggregate(features, edge_index, edge_attributes, gate_layer):
                count = features.new_zeros((features.shape[0], 1))
                total = features.new_zeros(features.shape)
                if edge_index.numel():
                    source, target = edge_index
                    weights = torch.sigmoid(gate_layer(edge_attributes))
                    total.index_add_(0, target, features[source] * weights)
                    count.index_add_(0, target, weights)
                return total / count.clamp_min(1.0)

            def forward(self, features, edge_index, edge_attributes):
                neighbor = self.aggregate(
                    features, edge_index, edge_attributes, self.edge_gate_1
                )
                hidden = torch.relu(
                    self.self_1(features) + self.neighbor_1(neighbor)
                )
                neighbor = self.aggregate(
                    hidden, edge_index, edge_attributes, self.edge_gate_2
                )
                embedding = torch.relu(
                    self.self_2(hidden) + self.neighbor_2(neighbor)
                )
                return {
                    "embedding": embedding,
                    "role_logits": self.role_head(embedding),
                    "consistency": torch.sigmoid(
                        self.consistency_head(embedding)
                    ).squeeze(-1),
                    "missing_label": torch.sigmoid(
                        self.missing_head(embedding)
                    ).squeeze(-1),
                    "incorrect_label": torch.sigmoid(
                        self.incorrect_head(embedding)
                    ).squeeze(-1),
                }

        return Model()


def _node_features(nodes: List[dict]) -> np.ndarray:
    values: List[List[float]] = []
    for node in nodes:
        features = node.get("features") or {}
        kind = str(node.get("kind") or "other")
        one_hot = [1.0 if kind == name else 0.0 for name in NODE_KINDS]
        values.append(
            [
                min(float(features.get("length") or node.get("length") or 0) / 500, 1),
                min(float(features.get("width") or node.get("width") or 0) / 200, 1),
                min(float(features.get("area") or node.get("area") or 0) / 50000, 1),
                (float(features.get("orientation") or node.get("orientation") or 0) % 180) / 180,
                min(float(features.get("font_size") or node.get("font_size") or 0) / 72, 1),
                *one_hot,
            ]
        )
    return np.asarray(values, dtype=np.float32)


def _checkpoint_edge_relations(checkpoint: Dict[str, Any]) -> tuple[str, ...]:
    """Relation vocabulary a checkpoint was trained with."""

    recorded = checkpoint.get("edge_relations")
    if recorded:
        return tuple(str(name) for name in recorded)
    weight = (checkpoint.get("state_dict") or {}).get("edge_gate_1.weight")
    if weight is not None:
        # Attribute vector is one-hot(relations) + [distance, reference].
        count = int(weight.shape[1]) - 2
        legacy = _LEGACY_EDGE_RELATIONS.get(count)
        if legacy:
            return legacy
    return EDGE_RELATIONS


def _edge_tensors(
    graph: Dict[str, Any],
    node_positions: Dict[str, int],
    *,
    max_edges: Optional[int] = None,
    relations: tuple[str, ...] = EDGE_RELATIONS,
) -> tuple[np.ndarray, np.ndarray]:
    pairs: List[tuple[int, int]] = []
    attributes: List[List[float]] = []
    edges = list(graph.get("edges") or [])
    if max_edges is not None and len(edges) > max_edges:
        # Prefer structural relations; keep training graphs tractable.
        priority = {
            "connected_to",
            "connected",
            "supports",
            "intersects",
            "nearest_label",
            "nearest_geometry",
            "inside",
            "touches",
            "same_tag",
            "reference",
        }
        preferred = [
            edge
            for edge in edges
            if str(edge.get("relationship") or edge.get("relation") or "")
            in priority
        ]
        remainder = [
            edge
            for edge in edges
            if str(edge.get("relationship") or edge.get("relation") or "")
            not in priority
        ]
        edges = (preferred + remainder)[:max_edges]
    for edge in edges:
        source = node_positions.get(str(edge.get("source")))
        target = node_positions.get(str(edge.get("target")))
        if source is None or target is None:
            continue
        relation = str(
            edge.get("relationship") or edge.get("relation") or "other"
        )
        # Normalize legacy CONNECTED edges onto CONNECTED_TO for GraphSAGE.
        if relation == "connected":
            relation = "connected_to"
        if relation not in relations:
            relation = "other"
        relation_vector = [1.0 if relation == name else 0.0 for name in relations]
        distance = min(float(edge.get("distance") or 0.0) / 500.0, 1.0)
        reference = float(
            edge.get("confidence")
            or edge.get("weight")
            or (1.0 if relation == "reference" else 0.0)
        )
        attribute = [*relation_vector, distance, min(reference, 1.0)]
        pairs.extend(((source, target), (target, source)))
        attributes.extend((attribute, attribute))
    edge_index = (
        np.asarray(pairs, dtype=np.int64).T
        if pairs
        else np.empty((2, 0), dtype=np.int64)
    )
    edge_attributes = (
        np.asarray(attributes, dtype=np.float32)
        if attributes
        else np.empty((0, len(relations) + 2), dtype=np.float32)
    )
    return edge_index, edge_attributes


def _load_runtime() -> Optional[tuple[Any, Any, Dict[str, Any]]]:
    global _RUNTIME
    path = settings.graphsage_model_path
    if not path.exists():
        return None
    with _LOCK:
        if _RUNTIME is None:
            torch = _torch()
            checkpoint = torch.load(path, map_location="cpu", weights_only=False)
            relations = _checkpoint_edge_relations(checkpoint)
            model = _GraphSAGEModel.create(
                int(checkpoint["input_dim"]),
                int(checkpoint["hidden_dim"]),
                len(checkpoint["role_labels"]),
                relation_count=len(relations),
            )
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()
            checkpoint["edge_relations"] = relations
            _RUNTIME = (torch, model, checkpoint)
    return _RUNTIME


def enrich_graph_embeddings(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Run trained GraphSAGE and attach learned node/source features."""

    try:
        runtime = _load_runtime()
    except (ImportError, RuntimeError, OSError, KeyError) as exc:
        runtime = None
        reason = str(exc)
    else:
        reason = "GraphSAGE checkpoint is not trained"
    if runtime is None:
        graph["graph_ai"] = {
            "available": False,
            "fallback": "constructed_graph_features",
            "reason": reason,
        }
        return graph
    torch, model, checkpoint = runtime
    nodes = graph.get("nodes") or []
    if not nodes:
        return graph
    positions = {
        str(node.get("node_id")): index for index, node in enumerate(nodes)
    }
    features = torch.from_numpy(
        np.ascontiguousarray(_node_features(nodes), dtype=np.float32)
    )
    edge_index, edge_attributes = _edge_tensors(
        graph, positions, relations=_checkpoint_edge_relations(checkpoint)
    )
    edges = torch.from_numpy(np.ascontiguousarray(edge_index)).long()
    edge_features = torch.from_numpy(np.ascontiguousarray(edge_attributes))
    with torch.inference_mode():
        output = model(features, edges, edge_features)
        role_probabilities = torch.softmax(output["role_logits"], dim=1)
    labels = checkpoint["role_labels"]
    source_features = graph.setdefault("source_features", {})
    for index, node in enumerate(nodes):
        role_index = int(role_probabilities[index].argmax().item())
        embedding = np.asarray(
            output["embedding"][index].cpu().tolist(), dtype=np.float32
        )
        embedding /= max(float(np.linalg.norm(embedding)), 1e-8)
        learned = {
            "graph_embedding": embedding.round(6).tolist(),
            "graph_confidence": round(
                float(role_probabilities[index, role_index]), 6
            ),
            "graph_prediction": str(labels[role_index]),
            "structural_consistency": round(
                float(output["consistency"][index]), 6
            ),
            "missing_label_probability": round(
                float(output["missing_label"][index]), 6
            ),
            "incorrect_label_probability": round(
                float(output["incorrect_label"][index]), 6
            ),
        }
        node.update(learned)
        source_id = node.get("source_id")
        if source_id:
            source_features.setdefault(str(source_id), {}).update(learned)
    graph["graph_ai"] = {
        "available": True,
        "model": "graphsage",
        "embedding_dimension": int(checkpoint["hidden_dim"]),
    }
    return graph


def train_graphsage(
    samples: Iterable[Dict[str, Any]],
    *,
    epochs: int = 25,
    hidden_dim: int = GRAPH_EMBEDDING_DIM,
    destination: Optional[str | Path] = None,
    max_train_edges: int = 12_000,
) -> Dict[str, Any]:
    """Train GraphSAGE from graph JSON plus reviewed node annotations.

    Large engineering graphs can exceed 90k edges. Rebuilding those tensors
    every epoch via Python lists made training appear hung, so tensors are
    prepared once and oversized edge sets are capped for the training pass.
    """

    if hidden_dim != GRAPH_EMBEDDING_DIM:
        raise ValueError(
            f"Graph embedding dimension must be {GRAPH_EMBEDDING_DIM}"
        )
    torch = _torch()
    prepared = []
    seen_signatures: set[tuple[int, int, int]] = set()
    for sample in samples:
        graph = sample.get("graph") or {}
        labels = sample.get("node_labels") or {}
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        if not nodes or not labels:
            continue
        # Duplicate PDF/Excel pairs and artifact copies share the same
        # topology; training each copy multiplies wall-clock for no gain.
        signature = (len(nodes), len(edges), len(labels))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        positions = {
            str(node.get("node_id")): index for index, node in enumerate(nodes)
        }
        features = np.ascontiguousarray(_node_features(nodes), dtype=np.float32)
        edge_index, edge_attributes = _edge_tensors(
            graph, positions, max_edges=max_train_edges
        )
        indices = []
        roles = []
        consistency = []
        missing = []
        incorrect = []
        for node_id, annotation in labels.items():
            if node_id not in positions:
                continue
            indices.append(positions[node_id])
            role = str(annotation.get("member_role") or "other")
            roles.append(
                ROLE_LABELS.index(role)
                if role in ROLE_LABELS
                else ROLE_LABELS.index("other")
            )
            consistency.append(float(annotation.get("consistent", 1.0)))
            missing.append(float(annotation.get("missing_label", 0.0)))
            incorrect.append(float(annotation.get("incorrect_label", 0.0)))
        if not indices:
            continue
        prepared.append(
            {
                "features": torch.from_numpy(features),
                "edge_index": torch.from_numpy(
                    np.ascontiguousarray(edge_index)
                ).long(),
                "edge_attributes": torch.from_numpy(
                    np.ascontiguousarray(edge_attributes)
                ),
                "indices": torch.tensor(indices, dtype=torch.long),
                "roles": torch.tensor(roles, dtype=torch.long),
                "consistency": torch.tensor(consistency, dtype=torch.float32),
                "missing": torch.tensor(missing, dtype=torch.float32),
                "incorrect": torch.tensor(incorrect, dtype=torch.float32),
            }
        )
    if not prepared:
        raise ValueError("No reviewed graph node labels were provided")
    input_dim = int(prepared[0]["features"].shape[1])
    model = _GraphSAGEModel.create(input_dim, hidden_dim, len(ROLE_LABELS))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    for _ in range(max(1, epochs)):
        for batch in prepared:
            output = model(
                batch["features"],
                batch["edge_index"],
                batch["edge_attributes"],
            )
            index_tensor = batch["indices"]
            loss = torch.nn.functional.cross_entropy(
                output["role_logits"][index_tensor],
                batch["roles"],
            )
            for key, target_key in (
                ("consistency", "consistency"),
                ("missing_label", "missing"),
                ("incorrect_label", "incorrect"),
            ):
                loss = loss + torch.nn.functional.binary_cross_entropy(
                    output[key][index_tensor],
                    batch[target_key],
                )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    path = Path(destination or settings.graphsage_model_path)
    torch.save(
        {
            "schema_version": "1.1",
            "model": "graphsage",
            "input_dim": input_dim,
            "hidden_dim": hidden_dim,
            "role_labels": ROLE_LABELS,
            # Recorded so a later EDGE_RELATIONS/NODE_KINDS change cannot
            # silently invalidate this checkpoint at inference time.
            "edge_relations": EDGE_RELATIONS,
            "node_kinds": NODE_KINDS,
            "state_dict": model.state_dict(),
        },
        path,
    )
    global _RUNTIME
    _RUNTIME = None
    return {
        "path": str(path),
        "graphs": len(prepared),
        "epochs": int(epochs),
        "max_train_edges": int(max_train_edges),
    }
