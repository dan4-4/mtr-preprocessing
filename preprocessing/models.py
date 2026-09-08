from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ResourceItem:
    item_id: str
    ks_number: int | None
    estimate_code: str | None
    resource_type: int | None
    justification_source: str | None
    ksr_code: str | None
    ksr_name: str | None
    name_raw: str
    unit_raw: str
    consumption: float | None
    base_price: float | None
    total_cost: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceItem:
        return cls(
            item_id=data["item_id"],
            ks_number=data.get("ks_number"),
            estimate_code=data.get("estimate_code"),
            resource_type=data.get("resource_type"),
            justification_source=data.get("justification_source"),
            ksr_code=data.get("ksr_code"),
            ksr_name=data.get("ksr_name"),
            name_raw=data["name_raw"],
            unit_raw=data["unit_raw"],
            consumption=data.get("consumption"),
            base_price=data.get("base_price"),
            total_cost=data.get("total_cost"),
        )


@dataclass
class Characteristics:
    material_type: str | None = None
    material: str | None = None
    grade: str | None = None
    dn: str | None = None
    peak_pressure: str | None = None
    max_temperature: str | None = None
    working_medium: str | None = None
    safety_class: str | None = None
    connection_type: str | None = None
    control_type: str | None = None  # extension vs schema v0.5: «Способ управления»
    dimensions: str | None = None
    standards: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def has_any(self) -> bool:
        return any(
            [
                self.material_type,
                self.material,
                self.grade,
                self.dn,
                self.peak_pressure,
                self.max_temperature,
                self.working_medium,
                self.safety_class,
                self.connection_type,
                self.control_type,
                self.dimensions,
                self.standards,
            ]
        )
