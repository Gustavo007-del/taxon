"""Generate a sample spreadsheet mirroring the real supplier file layout.

Output (data/Product_List_sample.xlsx) uses the real file's column headers:
Product Number, Model Number, Product Category, Product Sub Category,
Collection Name, Product Color, Product Name, Product Description,
Bullets, Materials, MSRP, and images spread across Image 1..Image N —
which is exactly how the real catalogue stores its (up to 20) images.

~150 rows are created, deliberately sprinkled with the edge cases the
pipeline must survive: duplicate product numbers, blank descriptions,
missing category columns, a fully empty text row, broken image URLs,
non-ASCII/emoji text, padded whitespace, a near-match sub-category
(fuzzy shortcut), NaN cells, multi-image rows, and currency prices.

Usage (needs pandas + openpyxl; no Django setup required):
    python scripts/make_sample_data.py [output_path]
"""
import sys
from pathlib import Path

import pandas as pd

# (title, category, sub_category, description, bullets, color, materials)
BASE = [
    ("Corner Sofa 3-Seater", "Furniture", "Sofas", "Modern grey fabric corner sofa with chaise longue, three-seater.", "Three-seater with chaise longue", "Grey", "fabric"),
    ("Velvet Armchair", "Furniture", "Armchairs", "Velvet-upholstered accent armchair with wooden legs.", "Accent armchair", "Blue", "velvet, wood"),
    ("Oak Dining Chair", "Furniture", "Dining Chairs", "Solid oak dining chair with cushioned seat.", "Cushioned seat", "Natural", "oak wood"),
    ("Ergonomic Office Chair", "Furniture", "Office Chairs", "Mesh-back ergonomic office chair with lumbar support.", "Adjustable height", "Black", "mesh, nylon"),
    ("Glass Coffee Table", "Furniture", "Coffee Tables", "Round tempered-glass coffee table, 80 cm diameter.", "Tempered glass top", "Clear", "glass, metal"),
    ("Extendable Dining Table", "Furniture", "Dining Tables", "Extendable oak dining table seating six to eight.", "Seats 6-8", "Oak", "oak wood"),
    ("Walnut Nightstand", "Furniture", "Nightstands", "Two-drawer walnut nightstand with soft-close runners.", "Two drawers", "Walnut", "walnut wood"),
    ("Classic White T-Shirt", "Apparel", "T-Shirts", "Cotton crew-neck t-shirt, regular fit, machine washable.", "Crew neck", "White", "cotton"),
    ("Slim Fit Jeans", "Apparel", "Jeans", "Slim-fit denim jeans with stretch, mid-rise.", "Mid-rise", "Blue", "denim, elastane"),
    ("Summer Floral Dress", "Apparel", "Dresses", "Lightweight floral-print summer dress, knee length.", "Floral print", "Multicolor", "polyester"),
    ("Waterproof Rain Jacket", "Apparel", "Jackets", "Waterproof hooded rain jacket with taped seams.", "Waterproof", "Yellow", "polyester"),
    ("Trail Running Shoes", "Footwear", "Running Shoes", "Lightweight trail running shoes with grippy outsole.", "Grippy outsole", "Green", "mesh, rubber"),
    ("Leather Sandals", "Footwear", "Sandals", "Genuine leather sandals with cushioned footbed.", "Cushioned footbed", "Brown", "leather"),
    ("Wireless Headphones", "Electronics", "Headphones", "Over-ear wireless headphones with active noise cancelling.", "Active noise cancelling", "Black", "plastic, metal"),
    ("Smart Speaker", "Electronics", "Smart Speakers", "Voice-controlled smart speaker with room-filling sound.", "Voice control", "Grey", "fabric, plastic"),
    ("HD Webcam", "Electronics", "Webcams", "1080p HD webcam with built-in microphone and privacy shutter.", "1080p", "Black", "plastic"),
    ("Mechanical Keyboard", "Electronics", "Keyboards", "RGB mechanical keyboard with hot-swappable switches.", "RGB backlit", "White", "plastic, metal"),
    ("Stand Blender", "Kitchen", "Blenders", "High-speed stand blender with 1.5 L jar.", "1.5 L jar", "Silver", "glass, plastic"),
    ("Drip Coffee Maker", "Kitchen", "Coffee Makers", "12-cup programmable drip coffee maker with timer.", "Programmable timer", "Black", "plastic, glass"),
    ("2-Slice Toaster", "Kitchen", "Toasters", "Two-slice stainless steel toaster with browning control.", "Browning control", "Silver", "stainless steel"),
    ("Chef's Knife Set", "Kitchen", "Kitchen Knives", "Stainless steel chef's knife set with wooden block.", "5-piece set", "Silver", "stainless steel, wood"),
    ("Brick Building Set", "Toys", "Building Toys", "600-piece interlocking brick building set.", "600 pieces", "Multicolor", "plastic"),
    ("Collectible Doll", "Toys", "Dolls", "Fashion collectible doll with posable joints.", "Poseable", "Pink", "plastic, fabric"),
    ("Family Board Game", "Toys", "Board Games", "Strategy board game for 2-6 players, ages 10+.", "2-6 players", "Blue", "cardboard, plastic"),
    ("Plush Teddy Bear", "Toys", "Stuffed Animals", "Extra-soft plush teddy bear, 40 cm tall.", "40 cm", "Brown", "plush"),
    ("Orthopedic Dog Bed", "Pet Supplies", "Dog Beds", "Washable orthopedic dog bed with memory foam.", "Memory foam", "Grey", "fabric, foam"),
    ("Cat Tree Tower", "Pet Supplies", "Cat Trees", "Multi-level cat tree with scratching posts and perch.", "Scratching posts", "Beige", "sisal, wood"),
    ("Aquarium Starter Kit", "Pet Supplies", "Aquariums", "20-gallon aquarium starter kit with filter and light.", "20 gallon", "Clear", "glass, plastic"),
    ("Parrot Cage", "Pet Supplies", "Bird Cages", "Spacious parrot cage with removable tray.", "Removable tray", "Black", "metal"),
    ("Non-Slip Yoga Mat", "Sports & Outdoors", "Yoga Mats", "Non-slip TPE yoga mat, 6 mm thick, with carry strap.", "6 mm thick", "Purple", "TPE"),
    ("Adjustable Dumbbell Set", "Sports & Outdoors", "Dumbbells", "Adjustable dumbbell set, 2.5-25 kg per pair.", "2.5-25 kg", "Black", "metal, plastic"),
    ("Folding Treadmill", "Sports & Outdoors", "Treadmills", "Folding treadmill with incline and heart-rate monitor.", "Folding", "Black", "metal, plastic"),
    ("City Commuter Bicycle", "Sports & Outdoors", "Bicycles", "Lightweight city commuter bicycle, 7-speed.", "7-speed", "Blue", "aluminum, rubber"),
    ("Adjustable Desk Lamp", "Home & Garden", "Desk Lamps", "LED desk lamp with adjustable arm and USB port.", "USB port", "White", "plastic, metal"),
    ("Scented Soy Candle", "Home & Garden", "Candles", "Hand-poured soy candle, 60-hour burn time.", "60-hour burn", "Cream", "soy wax, glass"),
    ("Laptop Backpack", "Accessories", "Backpacks", "Water-resistant laptop backpack with padded sleeve.", "Fits 15\" laptop", "Black", "polyester"),
    ("Polarized Sunglasses", "Accessories", "Sunglasses", "Polarized UV400 sunglasses with hard case.", "UV400", "Black", "plastic, glass"),
    ("Automatic Wrist Watch", "Accessories", "Watches", "Automatic mechanical wrist watch, sapphire glass.", "Automatic movement", "Silver", "stainless steel, sapphire"),
    ("Ceramic Mug Set", "Home & Garden", "Mugs", "Set of four 350 ml ceramic mugs, dishwasher safe.", "Set of 4", "White", "ceramic"),
    ("Cotton Bed Sheet Set", "Home & Garden", "Bed Sheets", "400-thread-count cotton queen bed sheet set.", "400 thread count", "White", "cotton"),
]

MODELS = [f"M{5000 + i}" for i in range(150)]
BRANDS = ["Acme Home", "Northwind", "Blue Sky", "Urban Nest", "Peak Goods", "Everyday Co.", "EcoLiving"]
MATERIALS_FALLBACK = ["cotton", "oak wood", "stainless steel", "polyester", "leather", "glass", "bamboo"]
COLLECTIONS = ["Everyday", "Metropolitan", "Outdoor Living", "Work & Study", "Playroom"]
COLORS = ["White", "Black", "Grey", "Brown", "Blue", "Green", "Red", "Natural", "Silver"]

BROKEN_URL = "https://example.invalid/this-image-does-not-exist.jpg"
IMAGE_COUNT = 20  # the real file has Image 1..Image 20


def image_url(seed, n):
    return f"https://picsum.photos/seed/{seed}-{n}/400/400"


def spread_images(row, first, count):
    """Put `count` images into Image <first>..Image <first+count-1> columns."""
    for n in range(1, IMAGE_COUNT + 1):
        if first <= n < first + count:
            row[f"Image {n}"] = image_url(row["__seed"], n)
        else:
            row[f"Image {n}"] = None
    return row


def build_rows():
    rows = []
    for i in range(150):
        title, cat, sub, desc, bullets, color, materials = BASE[i % len(BASE)]
        row = {
            "Product Number": f"EEI-{i + 1:04d}",
            "Model Number": MODELS[i],
            "Product Category": cat,
            "Product Sub Category": sub,
            "Collection Name": COLLECTIONS[i % len(COLLECTIONS)],
            "Color Collection": COLORS[i % len(COLORS)],
            "Product Color": color,
            "Product Name": title,
            "Product Description": desc,
            "Bullets": bullets,
            "Materials": materials if i % 3 else MATERIALS_FALLBACK[i % len(MATERIALS_FALLBACK)],
            "MSRP": f"{(49.99 + (i % 40) * 3.5):.2f}",
            "Product URL": f"https://modwayfurniture.com/search?q=EEI-{i + 1:04d}",
            "__seed": i + 1,
        }
        rows.append(row)
    for idx, row in enumerate(rows):
        # Vary image counts: most rows 1-3 images, some none.
        spread_images(row, 1, 1 + (idx % 3) if idx % 7 else 0)
        row.pop("__seed")
    return rows


def apply_edge_cases(rows):
    """Overwrite specific rows with edge cases the importer must survive."""
    edge_cases = []

    # Duplicate product numbers (importer must skip the second occurrence).
    rows[0]["Product Number"] = "EEI-0001"
    rows[1]["Product Number"] = "EEI-0001"
    edge_cases.append("rows 0-1: duplicate product number EEI-0001")

    # Blank descriptions.
    for idx in range(10, 20):
        rows[idx]["Product Description"] = None
    edge_cases.append("rows 10-19: blank descriptions")

    # Missing category columns.
    for idx in range(20, 25):
        rows[idx]["Product Category"] = None
        rows[idx]["Product Sub Category"] = None
    edge_cases.append("rows 20-24: missing category columns")

    # Fully empty text row (image-only candidate).
    row = rows[25]
    for key in ("Product Name", "Product Description", "Product Category",
                "Product Sub Category", "Bullets", "Materials", "Product Color"):
        row[key] = None
    row["Image 1"] = image_url(999, 1)
    edge_cases.append("row 25: all text empty")

    # Broken image URLs (must be skipped, not crash the image pass).
    for idx in range(30, 35):
        rows[idx]["Image 1"] = BROKEN_URL
        rows[idx]["Image 2"] = None
    edge_cases.append("rows 30-34: broken image URLs")

    # Non-ASCII / emoji text.
    rows[40]["Product Name"] = "Café de Olla Mug ☕"
    rows[40]["Product Description"] = "Металлическая кружка для кофе 300 мл · 日本語対応商品 🎉"
    edge_cases.append("row 40: non-ASCII + emoji text")

    # Whitespace-padded values (importer must strip).
    for idx in range(45, 50):
        rows[idx]["Product Name"] = f"  {rows[idx]['Product Name']}  "
    edge_cases.append("rows 45-49: padded whitespace in titles")

    # Near-match sub-category ("T-Shirt" vs taxonomy "T-Shirts") — fuzzy shortcut.
    rows[50]["Product Sub Category"] = "T-Shirt"
    edge_cases.append("row 50: near-match sub-category (fuzzy shortcut)")

    # NaN materials.
    for idx in range(55, 60):
        rows[idx]["Materials"] = None
    edge_cases.append("rows 55-59: NaN materials")

    # Multi-image row: three images across Image 1..Image 3.
    for n in range(1, 4):
        rows[60][f"Image {n}"] = image_url(777, n)
    edge_cases.append("row 60: three images in Image 1..3")

    # Currency-formatted MSRP values.
    rows[65]["MSRP"] = "$49.99"
    rows[66]["MSRP"] = "1,299.00"
    edge_cases.append("rows 65-66: currency-formatted prices")

    return edge_cases


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/Product_List_sample.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = build_rows()
    edge_cases = apply_edge_cases(rows)
    df = pd.DataFrame(rows)
    # Empty string cells would otherwise become NaN; pandas writes them as
    # empty cells, which the importer treats identically to NaN.
    df.to_excel(out, index=False)

    print(f"Wrote {len(df)} rows to {out}")
    print(f"Columns ({len(df.columns)}): {', '.join(str(c) for c in df.columns)}")
    print("Edge cases included:")
    for case in edge_cases:
        print(f"  - {case}")


if __name__ == "__main__":
    main()
