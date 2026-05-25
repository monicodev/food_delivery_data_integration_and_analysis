import pytest
import os

try:
    from src.engine.image_processor import ImageProcessor
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

from src.config import Config


@pytest.mark.skipif(not HAS_DEPS, reason="cv2/transformers/torch not installed")
def test_image_processor_invalid_cid():
    processor = ImageProcessor(image_root=str(Config.GOOGLE_IMAGES_DIR))
    result = processor.process_venue("non_existent_cid_123")

    assert "error" in result
    assert "No images found" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__])
