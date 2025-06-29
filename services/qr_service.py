from PIL import Image
from pyzbar.pyzbar import decode
import io


class QRService:
    def __init__(self):
        pass

    def decode_qr(self, image_data: bytes) -> str:
        """Decode QR code from image data."""
        try:
            # Convert bytes to image
            image = Image.open(io.BytesIO(image_data))

            # Decode QR codes
            decoded_objects = decode(image)

            if not decoded_objects:
                return None

            # Return the first QR code data
            return decoded_objects[0].data.decode("utf-8")

        except Exception as e:
            print(f"Error decoding QR code: {e}")
            return None

    def parse_qr_data(self, qr_data: str) -> dict:
        # TODO
        ...
