"""Generate a small sample spreadsheet (data/Product_List_sample.xlsx).

Creates ~150 rows in the same shape as the real supplier file, deliberately
sprinkled with the edge cases the pipeline must survive:
duplicate product numbers, blank descriptions, missing category columns,
a fully empty text row, broken image URLs, non-ASCII/emoji text, padded
whitespace, a near-match sub-category (fuzzy shortcut), NaN cells,
multi-image rows, and currency-formatted prices.

Usage (needs pandas + openpyxl; no Django setup required):
    python scripts/make_sample_data.py [output_path]
"""
import sys
from pathlib import Path

import pandas as pd

# (title, category_raw, sub_category_raw, description)
BASE = [
    ("Corner Sofa 3-Seater", "Furniture", "Sofas", "Modern grey fabric corner sofa with chaise longue, three-seater."),
    ("Velvet Armchair", "Furniture", "Armchairs", "Velvet-upholstered accent armchair with wooden legs."),
    ("Oak Dining Chair", "Furniture", "Dining Chairs", "Solid oak dining chair with cushioned seat."),
    ("Ergonomic Office Chair", "Furniture", "Office Chairs", "Mesh-back ergonomic office chair with lumbar support."),
    ("Glass Coffee Table", "Furniture", "Coffee Tables", "Round tempered-glass coffee table, 80 cm diameter."),
    ("Extendable Dining Table", "Furniture", "Dining Tables", "Extendable oak dining table seating six to eight."),
    ("Walnut Nightstand", "Furniture", "Nightstands", "Two-drawer walnut nightstand with soft-close runners."),
    ("Classic White T-Shirt", "Apparel", "T-Shirts", "Cotton crew-neck t-shirt, regular fit, machine washable."),
    ("Slim Fit Jeans", "Apparel", "Jeans", "Slim-fit denim jeans with stretch, mid-rise."),
    ("Summer Floral Dress", "Apparel", "Dresses", "Lightweight floral-print summer dress, knee length."),
    ("Waterproof Rain Jacket", "Apparel", "Jackets", "Waterproof hooded rain jacket with taped seams."),
    ("Trail Running Shoes", "Footwear", "Running Shoes", "Lightweight trail running shoes with grippy outsole."),
    ("Leather Sandals", "Footwear", "Sandals", "Genuine leather sandals with cushioned footbed."),
    ("Wireless Headphones", "Electronics", "Headphones", "Over-ear wireless headphones with active noise cancelling."),
    ("Smart Speaker", "Electronics", "Smart Speakers", "Voice-controlled smart speaker with room-filling sound."),
    ("HD Webcam", "Electronics", "Webcams", "1080p HD webcam with built-in microphone and privacy shutter."),
    ("Mechanical Keyboard", "Electronics", "Keyboards", "RGB mechanical keyboard with hot-swappable switches."),
    ("Stand Blender", "Kitchen", "Blenders", "High-speed stand blender with 1.5 L jar."),
    ("Drip Coffee Maker", "Kitchen", "Coffee Makers", "12-cup programmable drip coffee maker with timer."),
    ("2-Slice Toaster", "Kitchen", "Toasters", "Two-slice stainless steel toaster with browning control."),
    ("Chef's Knife Set", "Kitchen", "Kitchen Knives", "Stainless steel chef's knife set with wooden block."),
    ("Brick Building Set", "Toys", "Building Toys", "600-piece interlocking brick building set."),
    ("Collectible Doll", "Toys", "Dolls", "Fashion collectible doll with posable joints."),
    ("Family Board Game", "Toys", "Board Games", "Strategy board game for 2-6 players, ages 10+."),
    ("Plush Teddy Bear", "Toys", "Stuffed Animals", "Extra-soft plush teddy bear, 40 cm tall."),
    ("Orthopedic Dog Bed", "Pet Supplies", "Dog Beds", "Washable orthopedic dog bed with memory foam."),
    ("Cat Tree Tower", "Pet Supplies", "Cat Trees", "Multi-level cat tree with scratching posts and perch."),
    ("Aquarium Starter Kit", "Pet Supplies", "Aquariums", "20-gallon aquarium starter kit with filter and light."),
    ("Parrot Cage", "Pet Supplies", "Bird Cages", "Spacious parrot cage with removable tray."),
    ("Non-Slip Yoga Mat", "Sports & Outdoors", "Yoga Mats", "Non-slip TPE yoga mat, 6 mm thick, with carry strap."),
    ("Adjustable Dumbbell Set", "Sports & Outdoors", "Dumbbells", "Adjustable dumbbell set, 2.5-25 kg per pair."),
    ("Folding Treadmill", "Sports & Outdoors", "Treadmills", "Folding treadmill with incline and heart-rate monitor."),
    ("City Commuter Bicycle", "Sports & Outdoors", "Bicycles", "Lightweight city commuter bicycle, 7-speed."),
    ("Adjustable Desk Lamp", "Home & Garden", "Desk Lamps", "LED desk lamp with adjustable arm and USB port."),
    ("Scented Soy Candle", "Home & Garden", "Candles", "Hand-poured soy candle, 60-hour burn time."),
    ("Laptop Backpack", "Accessories", "Backpacks", "Water-resistant laptop backpack with padded sleeve."),
    ("Polarized Sunglasses", "Accessories", "Sunglasses", "Polarized UV400 sunglasses with hard case."),
    ("Automatic Wrist Watch", "Accessories", "Watches", "Automatic mechanical wrist watch, sapphire glass."),
    ("Ceramic Mug Set", "Home & Garden", "Mugs", "Set of four 350 ml ceramic mugs, dishwasher safe."),
    ("Cotton Bed Sheet Set", "Home & Garden", "Bed Sheets", "400-thread-count cotton queen bed sheet set."),
]

BRANDS = ["Acme Home", "Northwind", "Blue Sky", "Urban Nest", "Peak Goods", "Everyday Co.", "EcoLiving"]
MATERIALS = ["cotton", "oak wood", "stainless steel", "polyester", "leather", "glass", "bamboo"]

BROKEN_URL = "https://example.invalid/this-image-does-not-exist.jpg"


def image_cell(seed, n=1):
    if n == 1:
        return f"https://picsum.photos/seed/{seed}/400/400"
    return ", ".join(f"https://picsum.photos/seed/{seed}-{i}/400/400" for i in range(n))


def build_rows():
    rows = []
    for i in range(150):
        title, cat, sub, desc = BASE[i % len(BASE)]
        rows.append(
            {
                "product_number": f"SKU-{i + 1:04d}",
                "title": title,
                "description": desc,
                "category_raw": cat,
                "sub_category_raw": sub,
                "brand": BRANDS[i % len(BRANDS)],
                "materials": MATERIALS[i % len(MATERIALS)],
                "image_urls": image_cell(i + 1),
                "price": f"{(9.99 + (i % 40) * 2.5):.2f}",
            }
        )
    return rows


def apply_edge_cases(rows):
    """Overwrite specific rows with the edge cases the importer must survive."""
    edge_cases = []

    # Duplicate product numbers (importer must skip the second occurrence).
    rows[0]["product_number"] = "SKU-0001"
    rows[1]["product_number"] = "SKU-0001"
    edge_cases.append("rows 0-1: duplicate product_number SKU-0001")

    # Blank descriptions.
    for idx in range(10, 20):
        rows[idx]["description"] = None
    edge_cases.append("rows 10-19: blank descriptions")

    # Missing category columns.
    for idx in range(20, 25):
        rows[idx]["category_raw"] = None
        rows[idx]["sub_category_raw"] = None
    edge_cases.append("rows 20-24: missing category columns")

    # Fully empty text row (image-only candidate).
    row = rows[25]
    for key in ("title", "description", "category_raw", "sub_category_raw", "brand", "materials"):
        row[key] = None
    row["image_urls"] = image_cell(999)
    edge_cases.append("row 25: all text empty")

    # Broken image URLs (must be skipped, not crash the image pass).
    for idx in range(30, 35):
        rows[idx]["image_urls"] = BROKEN_URL
    edge_cases.append("rows 30-34: broken image URLs")

    # Non-ASCII / emoji text.
    rows[40]["title"] = "Café de Olla Mug ☕"
    rows[40]["description"] = "Металлическая кружка для кофе 300 мл · 日本語対応商品 🎉"
    edge_cases.append("row 40: non-ASCII + emoji text")

    # Whitespace-padded values (importer must strip).
    for idx in range(45, 50):
        rows[idx]["title"] = f"  {rows[idx]['title']}  "
    edge_cases.append("rows 45-49: padded whitespace in titles")

    # Near-match sub-category ("T-Shirt" vs taxonomy "T-Shirts") — fuzzy shortcut.
    rows[50]["sub_category_raw"] = "T-Shirt"
    edge_cases.append("row 50: near-match sub-category (fuzzy shortcut)")

    # NaN materials.
    for idx in range(55, 60):
        rows[idx]["materials"] = None
    edge_cases.append("rows 55-59: NaN materials")

    # Multi-image row.
    rows[60]["image_urls"] = image_cell(777, n=3)
    edge_cases.append("row 60: three image URLs in one cell")

    # Currency-formatted prices.
    rows[65]["price"] = "$49.99"
    rows[66]["price"] = "1,299.00"
    edge_cases.append("rows 65-66: currency-formatted prices")

    return edge_cases


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/Product_List_sample.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = build_rows()
    edge_cases = apply_edge_cases(rows)
    df = pd.DataFrame(rows)
    df.to_excel(out, index=False)

    print(f"Wrote {len(df)} rows to {out}")
    print("Edge cases included:")
    for case in edge_cases:
        print(f"  - {case}")


if __name__ == "__main__":
    main()