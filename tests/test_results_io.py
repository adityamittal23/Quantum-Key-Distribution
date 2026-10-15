import pandas as pd
import pytest

from qkd.results_io import read_results_csv, write_results_csv


def test_round_trip_keeps_metadata_and_adds_seed_column(tmp_path):
    df = pd.DataFrame({"p": [0.0, 0.5], "qber": [0.0, 0.125]})
    path = write_results_csv(df, "unit_test", seed=42, params={"n": 1000}, results_dir=tmp_path)
    meta, table = read_results_csv(path)
    assert meta["experiment"] == "unit_test"
    assert meta["seed"] == 42
    assert meta["params"] == {"n": 1000}
    assert "qiskit" in meta["versions"]
    assert table["seed"].tolist() == [42, 42]
    assert table["qber"].tolist() == [0.0, 0.125]


def test_existing_seed_column_is_kept(tmp_path):
    df = pd.DataFrame({"qber": [0.1, 0.2], "seed": [7, 8]})
    _, table = read_results_csv(write_results_csv(df, "seeds", 1, {}, tmp_path))
    assert table["seed"].tolist() == [7, 8]


@pytest.mark.parametrize("name", ["../escape", "a b", ""])
def test_unsafe_names_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        write_results_csv(pd.DataFrame({"x": [1]}), name, 0, {}, tmp_path)


def test_empty_table_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        write_results_csv(pd.DataFrame(), "empty", 0, {}, tmp_path)
