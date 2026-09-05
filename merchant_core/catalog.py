import json
from typing import List, Optional
from pydantic import BaseModel
import config

class Product(BaseModel):
    id: str
    name: str
    description: str
    price_paise: int
    category: str
    stock: int
    image_emoji: str
    upsell_ids: List[str]

def load_catalog() -> List[Product]:
    """Loads catalog from data/catalog.json."""
    catalog_path = config.DATA_DIR / 'catalog.json'
    if not catalog_path.exists():
        return []
    with open(catalog_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [Product(**item) for item in data]

def search_products(query: Optional[str] = None, category: Optional[str] = None, max_price_paise: Optional[int] = None) -> List[Product]:
    """Searches products based on criteria."""
    catalog = load_catalog()
    results = []
    for p in catalog:
        if category and p.category.lower() != category.lower():
            continue
        if max_price_paise is not None and p.price_paise > max_price_paise:
            continue
        if query:
            q = query.lower()
            if q not in p.name.lower() and q not in p.description.lower():
                continue
        results.append(p)
    return results

def get_product(product_id: str) -> Optional[Product]:
    """Looks up a single product by ID."""
    catalog = load_catalog()
    for p in catalog:
        if p.id == product_id:
            return p
    return None

def get_upsells(product_id: str) -> List[Product]:
    """Returns the actual Product objects for each upsell_id."""
    product = get_product(product_id)
    if not product:
        return []
    return [p for p in load_catalog() if p.id in product.upsell_ids]

def get_categories() -> List[str]:
    """Returns unique category names."""
    return list(set(p.category for p in load_catalog()))
