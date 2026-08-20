from pathlib import Path
import json

import numpy as np
from PIL import Image

from refract.analysis import AnalysisPackBuilder, TechnicalAnalyzer


def test_technical_analyzer_measures_source(tmp_path):
    arr = np.zeros((120, 160, 3), dtype=np.uint8)
    arr[:, :80] = [10, 20, 30]
    arr[:, 80:] = [220, 180, 80]
    path = tmp_path / "sample.jpg"
    Image.fromarray(arr).save(path, quality=100)

    result = TechnicalAnalyzer().analyze(path)

    assert result.source.width == 160
    assert result.source.height == 120
    assert len(result.source.sha256) == 64
    assert result.technical.sharpness_score >= 0
    assert 0 <= result.technical.wb_confidence <= 1
    assert result.technical.clipped_highlights_pct >= 0


def test_technical_analyzer_converts_to_domain(tmp_path):
    path = tmp_path / "sample.png"
    Image.new("RGB", (40, 30), (80, 100, 120)).save(path)
    analyzer = TechnicalAnalyzer()
    source, technical = analyzer.to_domain(analyzer.analyze(path))
    assert source.width == 40
    assert technical.white_balance in {"cool", "neutral", "warm", "mixed", "unknown"}


def test_analysis_pack_uses_native_resolution_crops(tmp_path):
    arr = np.zeros((400, 600, 3), dtype=np.uint8)
    arr[:200, :300] = 30
    arr[:200, 300:] = 240
    for y in range(200, 400):
        arr[y, :, :] = ((np.arange(600) % 2) * 180 + 30)[:, None]
    src = tmp_path / "sample.png"
    Image.fromarray(arr).save(src)

    manifest = AnalysisPackBuilder(proxy_long_edge=256).build(src, tmp_path / "pack")

    assert Path(manifest.proxy_path).exists()
    assert {crop.role for crop in manifest.crops} == {"subject", "highlight", "shadow", "detail"}
    assert all(crop.width > 100 for crop in manifest.crops)
    data = json.loads((tmp_path / "pack" / "manifest.json").read_text())
    assert data["source_width"] == 600
