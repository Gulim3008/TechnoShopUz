CATEGORIES = {
    "phones": {
        "name": "📱 Monobloclar",
        "products": [
            {"id": 1, "name": "iPhone 14", "price": "12000000", "description": "128GB, kafolat 12 oy"},
            {"id": 2, "name": "Samsung A52", "price": "8500000", "description": "128GB, kafolat 12 oy"},
        ]
    },
    "printers": {
        "name": "🖨 PRINTERLAR",
        "products": [
            {"id": 3, "name": "Epson TM-T88VII", "price": "5200000", "description": "80mm chek printer"},
            {"id": 4, "name": "Star Micronics", "price": "4800000", "description": "58/80mm chek"},
        ]
    },
    "scanners": {
        "name": "📠 SCANERLAR",
        "products": [
            {"id": 5, "name": "Fujitsu iX1500", "price": "6800000", "description": "A4 skaner, 30 sahifa/minut"},
            {"id": 6, "name": "Canon DR-C225", "price": "5500000", "description": "A4/A6, 25 sahifa/minut"},
        ]
    },
    "software": {
        "name": "💻 PROGRAMMALAR",
        "products": [
            {"id": 7, "name": "1C Buxgalteriya", "price": "2500000", "description": "Buxgalteriya dasturi"},
            {"id": 8, "name": "Microsoft Office", "price": "1800000", "description": "Word, Excel, Outlook"},
        ]
    },
    "scales": {
        "name": "⚖️ TAROZILAR",
        "products": [
            {"id": 9, "name": "A&D SL-300K", "price": "3500000", "description": "Elektron taroziy, 300kg"},
            {"id": 10, "name": "Cas CL5500-15B", "price": "4200000", "description": "Zerikoşka, 15kg"},
        ]
    }
}

def get_product(product_id):
    for category in CATEGORIES.values():
        for p in category["products"]:
            if p["id"] == product_id:
                return p
    return None

def get_all_products():
    all_products = []
    for category in CATEGORIES.values():
        all_products.extend(category["products"])
    return all_products
