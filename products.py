PRODUCTS = [
    {"id": 1, "name": "Dell MonoBlock", "price": "25000000", "description": "24 inch monitor, Intel i5", "image": None},
    {"id": 2, "name": "Epson TM-T88VII", "price": "5200000", "description": "80mm chek printer, USB", "image": None},
    {"id": 3, "name": "Zebra ZD420", "price": "8500000", "description": "203 dpi label printer", "image": None},
    {"id": 4, "name": "Fujitsu iX1500", "price": "6800000", "description": "A4 skaner, 30 sahifa/minut", "image": None},
    {"id": 5, "name": "1C Buxgalteriya", "price": "2500000", "description": "Buxgalteriya va hisobvarislik", "image": None},
]

def get_product(product_id):
    for p in PRODUCTS:
        if p["id"] == product_id:
            return p
    return None
