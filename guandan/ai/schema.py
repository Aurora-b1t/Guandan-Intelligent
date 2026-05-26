"""Schema-driven configuration for AI models.

Register models with typed params. SchemaBuilder generates JSON
that the frontend uses to auto-render config forms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Param:
    """A single configurable parameter."""
    type: str                    # "int" | "float" | "select" | "ref"
    default: Any
    label: str = ""
    step: float = 0.5            # for float params
    options: Dict[str, str] = None  # for "select": {value: label}
    ref_category: str = ""       # for "ref": which category to look up


@dataclass
class ModelDef:
    """Definition of one selectable model."""
    name: str
    description: str = ""
    params: Dict[str, Param] = field(default_factory=dict)
    needs_full_info: bool = False
    is_mc: bool = False


@dataclass
class CategoryDef:
    """A category of models (e.g. decider, inner_model, enumerator)."""
    id: str
    label: str
    description: str = ""
    models: Dict[str, ModelDef] = field(default_factory=dict)


class SchemaBuilder:
    """Collects category definitions and generates JSON schema."""

    def __init__(self):
        self._categories: Dict[str, CategoryDef] = {}

    def category(self, cat_id: str, label: str, description: str = "") -> CategoryDef:
        c = CategoryDef(id=cat_id, label=label, description=description)
        self._categories[cat_id] = c
        return c

    def model(self, cat_id: str, model_id: str, name: str,
              description: str = "", **kw) -> ModelDef:
        m = ModelDef(name=name, description=description, **kw)
        self._categories[cat_id].models[model_id] = m
        return m

    def param(self, model: ModelDef, key: str, ptype: str,
              default: Any, label: str = "", **kw) -> Param:
        p = Param(type=ptype, default=default, label=label or key, **kw)
        model.params[key] = p
        return p

    def to_json(self) -> dict:
        """Generate JSON schema for the frontend."""
        categories = {}
        for cat_id, cat in self._categories.items():
            models = {}
            for mid, m in cat.models.items():
                params = {}
                for pkey, p in m.params.items():
                    pdef = {"type": p.type, "default": p.default, "label": p.label}
                    if p.step != 0.5:
                        pdef["step"] = p.step
                    if p.options:
                        pdef["options"] = p.options
                    if p.ref_category:
                        pdef["ref_category"] = p.ref_category
                    params[pkey] = pdef
                models[mid] = {
                    "name": m.name,
                    "description": m.description,
                    "needs_full_info": m.needs_full_info,
                    "is_mc": m.is_mc,
                    "params": params,
                }
            categories[cat_id] = {
                "label": cat.label,
                "description": cat.description,
                "models": models,
            }
        return categories
