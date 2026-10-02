"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Vehicle
from .const import DOMAIN
from .coordinator import ToyotaCoordinator, VehicleData


class ToyotaEntity(CoordinatorEntity[ToyotaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ToyotaCoordinator, v: Vehicle, key: str) -> None:
        super().__init__(coordinator)
        vin = self.vin = v.vin
        self._attr_unique_id = f"{vin}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            manufacturer="Toyota",
            model=" ".join(filter(None, (v.model, v.trim))),
            name=" ".join(filter(None, (v.model, v.plate))),
            model_id=v.car_id or None,
            serial_number=vin,
            hw_version=str(v.year) if v.year else None,
        )

    @property
    def vehicle_data(self) -> VehicleData | None:
        return self.coordinator.data.get(self.vin) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self.vehicle_data is not None
