"""Opening user images safely: refuse huge ones before decoding and decode JPEGs at reduced size.

A 13,000 x 13,000 image decodes to ~500 MB, enough to take down the 512 MB server. The pixel size is read from the
file header before any decoding, so oversized images are refused cheaply.
"""

import io
import threading
import warnings

from PIL import Image

import pillow_heif

pillow_heif.register_heif_opener()

MAX_PIXELS = 60_000_000  # a 48 MP phone photo (8064 x 6048 = 48.8 M) fits; a 13,000 px square doesn't
Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # Pillow's own guard, as a backstop


# One decode at a time: a 48 MP HEIC or PNG takes a couple of hundred MB while it's open, and two at once would
# run the 512 MB server out of memory.
_decoding = threading.BoundedSemaphore(1)


class ImageTooLarge(ValueError):
    pass


def open_image(data: bytes, max_side: int | None = None) -> Image.Image:
    """Open and fully load an image no bigger than MAX_PIXELS, decoding JPEGs straight at about `max_side`."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            im = Image.open(io.BytesIO(data))
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
            raise ImageTooLarge("That image is too large (over 60 megapixels).") from e
    w, h = im.size
    if w * h > MAX_PIXELS:
        raise ImageTooLarge("That image is too large (over 60 megapixels).")
    if max_side and im.format == "JPEG":
        im.draft("RGB", (max_side, max_side))  # JPEG decodes at 1/2, 1/4 or 1/8 scale: far less memory
    with _decoding:
        im.load()
        if max_side and max(im.size) > max_side:
            im.thumbnail((max_side, max_side))  # shrink before the caller copies it (convert, rotate)
    return im
