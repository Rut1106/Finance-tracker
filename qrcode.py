import qrcode
from PIL import Image, ImageDraw

def create_qr(
    url,
    filename="qr_code.png",
    qr_color="#ff751f",
    bg_color="white",
    border_radius=40,
    padding=50
):
    # Generate QR Code
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )

    qr.add_data(url)
    qr.make(fit=True)

    qr_img = qr.make_image(
        fill_color=qr_color,
        back_color=bg_color
    ).convert("RGBA")

    qr_width, qr_height = qr_img.size

    # Canvas size
    canvas_width = qr_width + padding * 2
    canvas_height = qr_height + padding * 2

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 0))

    # Rounded white background
    rounded = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(rounded)

    draw.rounded_rectangle(
        [(0, 0), (canvas_width, canvas_height)],
        radius=border_radius,
        fill="white"
    )

    canvas = Image.alpha_composite(canvas, rounded)

    # Paste QR in center
    canvas.paste(qr_img, (padding, padding), qr_img)

    # Save PNG
    canvas.save(filename)

    print(f"Saved: {filename}")


# Example
create_qr(
    "https://icp.utdallas.edu/cultural-heritage-months/",
    "CHM_qr.png"
)