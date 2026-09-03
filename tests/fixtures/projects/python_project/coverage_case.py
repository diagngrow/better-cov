from src.module import Worker, alpha


def test_selected_functions() -> None:
    assert alpha() == 1
    assert Worker().beta() == 2
