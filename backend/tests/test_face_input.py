from io import BytesIO

import pytest
from app.face_engine import FaceEngine, FaceInputError
from PIL import Image


def image_bytes(width=320, height=240):
    output=BytesIO()
    Image.new("RGB", (width,height), "white").save(output, format="JPEG")
    return output.getvalue()


def test_decode_valid_jpeg():
    assert FaceEngine.decode(image_bytes()).shape == (240,320,3)


@pytest.mark.parametrize("data,code", [(b"", "invalid_file_size"), (b"not an image", "invalid_image"), (image_bytes(2001,2001), "invalid_image_dimensions"), (image_bytes(20,20), "invalid_image_dimensions")])
def test_reject_unsafe_image_input(data,code):
    with pytest.raises(FaceInputError) as error:
        FaceEngine.decode(data)
    assert error.value.code == code


def test_reject_oversized_upload_before_decode():
    with pytest.raises(FaceInputError,match="invalid_file_size"):
        FaceEngine.decode(b"x"*101,max_bytes=100)
