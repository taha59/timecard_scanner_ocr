from pathlib import Path
import pytest

def pytest_collection_modifyitems(items):
    root=Path(__file__).parents[1]
    if (root/'fixtures/timecards.jpg').exists():
        return
    photo_api={'test_scan_calculate_and_training','test_manual_mode','test_new_photos_scan_without_ocr_or_network'}
    for item in items:
        module=Path(str(item.fspath)).name
        needs_photo=(module=='test_layout.py' and item.originalname!='test_unverified_green_rectangle_cannot_create_an_estimated_grid') or (module=='test_api.py' and item.originalname in photo_api)
        if needs_photo:
            item.add_marker(pytest.mark.skip(reason='Private photo fixtures are not included in the public repository'))
