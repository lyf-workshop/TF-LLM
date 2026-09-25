from types import SimpleNamespace

import pytest

from utu.practice import data_manager


def test_full_epoch_keeps_every_task_once_with_existing_mistakes(monkeypatch):
    dataset = "DAPO-fixed-200"
    datapoints = [
        SimpleNamespace(
            dataset=dataset,
            index=index,
            source="math",
            question=f"Question {index}",
            answer=str(index),
            level=None,
            file_name=None,
            meta={},
        )
        for index in range(3)
    ]

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def exec(self, _query):
            return SimpleNamespace(all=lambda: datapoints)

    class Mistakes:
        def __init__(self, exp_id):
            self.records = {f"{dataset}::0": SimpleNamespace(status="failed")}

        def load(self):
            pass

    monkeypatch.setattr(data_manager.SQLModelUtils, "create_session", lambda: Session())
    monkeypatch.setattr(data_manager, "MistakeBank", Mistakes)
    manager = data_manager.TrainingFreeGRPODataManager.__new__(data_manager.TrainingFreeGRPODataManager)
    manager.config = SimpleNamespace(exp_id="fixed-epoch", pass_k=2, data=SimpleNamespace(dataset=dataset))
    monkeypatch.setattr(manager, "_check_exp_id", lambda _exp_id: False)
    monkeypatch.setattr(manager, "save", lambda _samples: None)

    samples = manager.load_epoch_data(epoch=1, shuffle=False, truncate=3)

    assert [sample.dataset_index for sample in samples] == [0, 0, 1, 1, 2, 2]
    markers = {
        sample.meta[data_manager.PRACTICE_DATA_LAYOUT_META_KEY]["fingerprint"]
        for sample in samples
    }
    assert len(markers) == 1


def configured_manager(*, allow_legacy=False):
    manager = data_manager.TrainingFreeGRPODataManager.__new__(data_manager.TrainingFreeGRPODataManager)
    manager.config = SimpleNamespace(
        exp_id="contract-run",
        pass_k=2,
        data=SimpleNamespace(dataset="dataset-a"),
    )
    manager.mistake_focus_ratio = 0.3
    manager.data_seed = 42
    manager.data_layout_context = {"batch_size": 10}
    manager.allow_legacy_epoch_cache = allow_legacy
    return manager


def contract_datapoints():
    return [
        SimpleNamespace(
            dataset="dataset-a",
            index=index,
            source="math",
            question=f"Question {index}",
            answer=str(index),
            level=None,
            file_name=None,
            meta={},
        )
        for index in range(2)
    ]


def test_epoch_cache_contract_rejects_parameter_drift():
    manager = configured_manager()
    datapoints = contract_datapoints()
    contract = manager._layout_contract(
        epoch=0,
        shuffle=False,
        truncate=2,
        datapoints=datapoints,
    )
    marker = {
        "fingerprint": manager._sha256(contract),
        "contract": contract,
        "sample_count": 4,
    }
    samples = [
        SimpleNamespace(
            dataset="dataset-a",
            meta={data_manager.PRACTICE_DATA_LAYOUT_META_KEY: marker},
        )
        for _ in range(4)
    ]

    changed = dict(contract, data_seed=99, effective_epoch_seed=99)
    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        manager._validate_existing_epoch_rows(
            samples,
            contract=changed,
            datapoints=datapoints,
            truncate=2,
        )


def test_legacy_epoch_cache_requires_explicit_hierarchy_resume_compatibility():
    datapoints = contract_datapoints()
    samples = [SimpleNamespace(dataset="dataset-a", meta={}) for _ in range(4)]
    strict_manager = configured_manager(allow_legacy=False)
    contract = strict_manager._layout_contract(
        epoch=0,
        shuffle=False,
        truncate=2,
        datapoints=datapoints,
    )

    with pytest.raises(RuntimeError, match="predate the data-layout contract"):
        strict_manager._validate_existing_epoch_rows(
            samples,
            contract=contract,
            datapoints=datapoints,
            truncate=2,
        )

    resume_manager = configured_manager(allow_legacy=True)
    resume_manager._validate_existing_epoch_rows(
        samples,
        contract=contract,
        datapoints=datapoints,
        truncate=2,
    )


def fingerprinted_samples(manager, datapoints, contract):
    identities = [manager._selected_datapoint_identity(item) for item in datapoints]
    base_marker = {
        "fingerprint": manager._sha256(contract),
        "contract": contract,
        "sample_count": len(datapoints) * manager.config.pass_k,
        "selected_task_sha256": manager._selected_task_multiset_fingerprint(identities),
        "selected_order_sha256": manager._sha256(identities),
    }
    samples = []
    for position, datapoint in enumerate(datapoints):
        for replica in range(manager.config.pass_k):
            samples.append(
                SimpleNamespace(
                    dataset=datapoint.dataset,
                    dataset_index=datapoint.index,
                    source=datapoint.source,
                    raw_question=datapoint.question,
                    correct_answer=datapoint.answer,
                    level=datapoint.level,
                    file_name=datapoint.file_name,
                    meta={
                        data_manager.PRACTICE_DATA_LAYOUT_META_KEY: {
                            **base_marker,
                            "selection_position": position,
                            "replica_index": replica,
                        }
                    },
                )
            )
    return samples


def test_epoch_cache_contract_detects_same_count_wrong_task_rows():
    manager = configured_manager()
    datapoints = contract_datapoints()
    contract = manager._layout_contract(
        epoch=0,
        shuffle=True,
        truncate=2,
        datapoints=datapoints,
    )
    samples = fingerprinted_samples(manager, datapoints, contract)
    manager._validate_existing_epoch_rows(
        samples,
        contract=contract,
        datapoints=datapoints,
        truncate=2,
    )

    for sample in samples[-2:]:
        sample.raw_question = "Polluted question"
    with pytest.raises(RuntimeError, match="multiset fingerprint mismatch"):
        manager._validate_existing_epoch_rows(
            samples,
            contract=contract,
            datapoints=datapoints,
            truncate=2,
        )


def test_get_batch_samples_restores_persisted_shuffle_order(monkeypatch):
    manager = configured_manager()
    datapoints = contract_datapoints()
    contract = manager._layout_contract(
        epoch=0,
        shuffle=True,
        truncate=2,
        datapoints=datapoints,
    )
    ordered = fingerprinted_samples(manager, list(reversed(datapoints)), contract)

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def exec(self, _query):
            # Simulate SQL's dataset_index ordering, opposite to selection order.
            return SimpleNamespace(all=lambda: list(reversed(ordered)))

    monkeypatch.setattr(data_manager.SQLModelUtils, "create_session", lambda: Session())

    samples = manager.get_batch_samples(epoch=0)

    assert [sample.dataset_index for sample in samples] == [1, 1, 0, 0]
