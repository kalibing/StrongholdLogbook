from io import BytesIO

from PIL import Image
import pytest

from logbook import accounts


def image_bytes(size, format="PNG", color=(200, 40, 40, 255)):
    output = BytesIO()
    mode = "RGBA" if format in {"PNG", "WEBP"} else "RGB"
    Image.new(mode, size, color[:len(mode)]).save(output, format=format)
    return output.getvalue()


def test_clean_name_normalizes_and_limits():
    assert accounts.clean_name("  夜  莺 ") == "夜 莺"
    assert accounts.clean_name("   ") is None
    assert accounts.clean_name(None) is None
    assert accounts.clean_name("一" * accounts.NAME_LIMIT) == "一" * accounts.NAME_LIMIT
    with pytest.raises(accounts.AccountError):
        accounts.clean_name("一" * (accounts.NAME_LIMIT + 1))
    with pytest.raises(accounts.AccountError):
        accounts.clean_name("bad​name")


def test_avatar_is_cropped_to_square_png():
    result = accounts.process_avatar(image_bytes((800, 400), "JPEG"))
    with Image.open(BytesIO(result)) as image:
        assert image.format == "PNG"
        assert image.size == (accounts.AVATAR_SIZE, accounts.AVATAR_SIZE)


@pytest.mark.parametrize("data", [b"", b"not an image", image_bytes((10, 10), "BMP")])
def test_avatar_rejects_invalid_input(data):
    with pytest.raises(accounts.AccountError):
        accounts.process_avatar(data)


def test_avatar_rejects_huge_dimensions():
    with pytest.raises(accounts.AccountError):
        accounts.process_avatar(image_bytes((accounts.AVATAR_EDGE + 1, 2), "PNG"))
