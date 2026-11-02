def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: GPU を使う試験（merge_lane.py は動かさない。声の窓だけが動かす）")
