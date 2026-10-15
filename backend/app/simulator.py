import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

from app.models import Patient, Reading
from app.store import Repository

PATIENT_NAMES = (
    "Avery Morgan",
    "Jordan Lee",
    "Casey Patel",
    "Riley Chen",
    "Taylor Kim",
    "Quinn Brooks",
    "Morgan Diaz",
    "Jamie Park",
    "Drew Wilson",
    "Alex Rivera",
    "Cameron Shah",
    "Skyler Reed",
)
SCENARIO_NAMES = (
    "spo2_decline",
    "tachycardia",
    "bp_spike",
    "sensor_dropout",
    "recovery",
)
SCENARIO_DURATION_TICKS = 10


class ActiveScenario:
    def __init__(self, name: str, duration_ticks: int) -> None:
        self.name = name
        self.remaining_ticks = duration_ticks
        self.elapsed_ticks = 0


class Simulator:
    def __init__(self, repository: Repository, seed: int = 42) -> None:
        self.repository = repository
        self._random = random.Random(seed)
        self._baselines: dict[str, dict[str, int]] = {}
        self._scenarios: dict[str, ActiveScenario] = {}
        self.tick_count = 0

    def seed(self) -> None:
        now = datetime.now(timezone.utc)
        for index, name in enumerate(PATIENT_NAMES, start=1):
            patient_id = f"P{index:03d}"
            patient = Patient(
                id=patient_id,
                name=name,
                age=self._random.randint(25, 85),
            )
            baseline = {
                "hr": self._random.randint(68, 76),
                "sys_bp": self._random.randint(116, 124),
                "dia_bp": self._random.randint(76, 84),
                "spo2": self._random.randint(96, 98),
            }
            self.repository.add_patient(patient)
            self._baselines[patient_id] = baseline

            for reading_index in range(30):
                ts = now - timedelta(seconds=(29 - reading_index) * 5)
                self.repository.add_reading(
                    Reading(
                        patient_id=patient_id,
                        ts=ts,
                        hr=baseline["hr"] + self._random.randint(-2, 2),
                        sys_bp=baseline["sys_bp"] + self._random.randint(-2, 2),
                        dia_bp=baseline["dia_bp"] + self._random.randint(-2, 2),
                        spo2=baseline["spo2"] + self._random.choice((-1, 0, 0, 1)),
                        quality="ok",
                    )
                )

    def tick(self) -> list[Reading]:
        self.tick_count += 1
        timestamp = datetime.now(timezone.utc)
        readings: list[Reading] = []

        for patient in self.repository.get_patients():
            baseline = self._baselines[patient.id]
            hr = baseline["hr"] + self._random.randint(-2, 2)
            sys_bp = baseline["sys_bp"] + self._random.randint(-2, 2)
            dia_bp = baseline["dia_bp"] + self._random.randint(-2, 2)
            spo2 = baseline["spo2"] + self._random.choice((-1, 0, 0, 1))
            quality = "ok"

            if patient.id == "P008" and self.tick_count >= 5:
                spo2 = max(80, baseline["spo2"] - (self.tick_count - 4))
            elif patient.id == "P009":
                hr = self._random.randint(133, 137)
            elif patient.id == "P010":
                sys_bp = self._random.randint(183, 187)
            elif patient.id == "P011":
                hr = sys_bp = dia_bp = spo2 = None
                quality = "missing"
            elif patient.id == "P012":
                spo2 = min(
                    baseline["spo2"],
                    89 + self.tick_count,
                )

            active_scenario = self._scenarios.get(patient.id)
            if active_scenario is not None:
                hr, sys_bp, dia_bp, spo2, quality = self._scenario_values(
                    active_scenario,
                    baseline,
                )
                active_scenario.elapsed_ticks += 1
                active_scenario.remaining_ticks -= 1
                if active_scenario.remaining_ticks == 0:
                    del self._scenarios[patient.id]
                    self.repository.add_patient(
                        patient.model_copy(update={"scenario": None})
                    )

            reading = Reading(
                patient_id=patient.id,
                ts=timestamp,
                hr=hr,
                sys_bp=sys_bp,
                dia_bp=dia_bp,
                spo2=spo2,
                quality=quality,
            )
            self.repository.add_reading(reading)
            readings.append(reading)

        return readings

    def trigger_scenario(
        self,
        name: str,
        patient_id: str,
        duration_ticks: int = SCENARIO_DURATION_TICKS,
    ) -> int:
        if name not in SCENARIO_NAMES:
            raise ValueError(f"Unknown scenario: {name}")
        patient = self.repository.get_patient(patient_id)
        if patient is None:
            raise KeyError(f"Unknown patient: {patient_id}")
        self._scenarios[patient_id] = ActiveScenario(name, duration_ticks)
        self.repository.add_patient(patient.model_copy(update={"scenario": name}))
        return duration_ticks

    def _scenario_values(
        self,
        scenario: ActiveScenario,
        baseline: dict[str, int],
    ) -> tuple[int | None, int | None, int | None, int | None, Literal["ok", "missing"]]:
        if scenario.name == "spo2_decline":
            return (
                baseline["hr"],
                baseline["sys_bp"],
                baseline["dia_bp"],
                max(80, baseline["spo2"] - scenario.elapsed_ticks - 1),
                "ok",
            )
        if scenario.name == "tachycardia":
            return 135, baseline["sys_bp"], baseline["dia_bp"], baseline["spo2"], "ok"
        if scenario.name == "bp_spike":
            return baseline["hr"], 185, baseline["dia_bp"], baseline["spo2"], "ok"
        if scenario.name == "sensor_dropout":
            return None, None, None, None, "missing"
        return (
            baseline["hr"],
            baseline["sys_bp"],
            baseline["dia_bp"],
            baseline["spo2"],
            "ok",
        )

    async def run(
        self,
        tick_seconds: int,
        on_tick: Callable[[list[Reading]], None] | None = None,
    ) -> None:
        while True:
            await asyncio.sleep(tick_seconds)
            readings = self.tick()
            if on_tick is not None:
                on_tick(readings)
