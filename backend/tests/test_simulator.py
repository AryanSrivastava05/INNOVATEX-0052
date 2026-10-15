from app.simulator import Simulator
from app.store import InMemoryRepository


def create_simulator() -> tuple[InMemoryRepository, Simulator]:
    repository = InMemoryRepository()
    simulator = Simulator(repository)
    simulator.seed()
    return repository, simulator


def test_seed_creates_twelve_patients_with_thirty_history_readings() -> None:
    repository, _ = create_simulator()

    assert [patient.id for patient in repository.get_patients()] == [
        f"P{index:03d}" for index in range(1, 13)
    ]
    assert all(
        len(repository.get_readings(patient.id)) == 30
        for patient in repository.get_patients()
    )


def test_seeded_history_and_ticks_are_reproducible() -> None:
    first_repository, first_simulator = create_simulator()
    second_repository, second_simulator = create_simulator()

    first_simulator.tick()
    second_simulator.tick()

    first_values = [
        (reading.hr, reading.sys_bp, reading.dia_bp, reading.spo2, reading.quality)
        for reading in first_repository.get_readings("P008")
    ]
    second_values = [
        (reading.hr, reading.sys_bp, reading.dia_bp, reading.spo2, reading.quality)
        for reading in second_repository.get_readings("P008")
    ]
    assert first_values == second_values


def test_normal_patients_remain_within_demo_thresholds() -> None:
    _, simulator = create_simulator()

    readings = simulator.tick()[:7]

    assert all(reading.quality == "ok" for reading in readings)
    assert all(50 <= reading.hr <= 110 for reading in readings)
    assert all(95 <= reading.sys_bp <= 160 for reading in readings)
    assert all(reading.spo2 >= 92 for reading in readings)


def test_p008_spo2_decline_begins_on_tick_five() -> None:
    repository, simulator = create_simulator()
    baseline_spo2 = simulator._baselines["P008"]["spo2"]

    for _ in range(4):
        simulator.tick()
    before_decline = repository.get_latest_reading("P008")
    tick_five = simulator.tick()[7]
    tick_six = simulator.tick()[7]

    assert before_decline is not None and before_decline.spo2 is not None
    assert tick_five.spo2 == baseline_spo2 - 1
    assert tick_six.spo2 == baseline_spo2 - 2


def test_default_abnormal_and_recovery_states() -> None:
    repository, simulator = create_simulator()

    first_tick = simulator.tick()
    second_tick = simulator.tick()
    patient_readings = {reading.patient_id: reading for reading in first_tick}

    assert patient_readings["P009"].hr >= 130
    assert patient_readings["P010"].sys_bp > 180
    assert patient_readings["P011"].quality == "missing"
    assert patient_readings["P011"].hr is None
    assert patient_readings["P011"].spo2 is None
    assert repository.get_latest_reading("P012").spo2 == 91
    assert next(reading for reading in second_tick if reading.patient_id == "P012").spo2 == 91


def test_scenarios_override_patient_generator_for_ten_ticks() -> None:
    repository, simulator = create_simulator()
    expected = {
        "spo2_decline": ("ok", None, None, None),
        "tachycardia": ("ok", 135, None, None),
        "bp_spike": ("ok", None, 185, None),
        "sensor_dropout": ("missing", None, None, None),
        "recovery": ("ok", None, None, None),
    }

    for scenario, (quality, expected_hr, expected_sys_bp, expected_spo2) in expected.items():
        simulator.trigger_scenario(scenario, "P002")
        reading = next(item for item in simulator.tick() if item.patient_id == "P002")
        assert reading.quality == quality
        if expected_hr is not None:
            assert reading.hr == expected_hr
        if expected_sys_bp is not None:
            assert reading.sys_bp == expected_sys_bp
        if expected_spo2 is not None:
            assert reading.spo2 == expected_spo2
        assert repository.get_patient("P002").scenario == scenario


def test_scenario_clears_patient_scenario_after_duration() -> None:
    repository, simulator = create_simulator()
    simulator.trigger_scenario("tachycardia", "P002", duration_ticks=2)

    simulator.tick()
    simulator.tick()

    assert repository.get_patient("P002").scenario is None
    assert simulator._scenarios.get("P002") is None
