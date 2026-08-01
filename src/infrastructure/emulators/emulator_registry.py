from typing import Mapping, Type

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.base_ammeter import AmmeterEmulatorBase


EMULATOR_REGISTRY: Mapping[str, Type[AmmeterEmulatorBase]] = {
    "greenlee": GreenleeAmmeter,
    "entes": EntesAmmeter,
    "circutor": CircutorAmmeter,
}
