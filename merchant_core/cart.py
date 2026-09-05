import uuid
from typing import Dict, List, Optional
from pydantic import BaseModel
from merchant_core.catalog import get_product

class CartItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price_paise: int
    total_price_paise: int

class CartResult(BaseModel):
    success: bool
    message: str

class CartView(BaseModel):
    items: List[CartItem]
    total_paise: int
    item_count: int

class Cart:
    # Session-scoped state: session_id -> list of CartItem
    _state: Dict[str, List[CartItem]] = {}

    @classmethod
    def _get_session_cart(cls, session_id: str) -> List[CartItem]:
        if session_id not in cls._state:
            cls._state[session_id] = []
        return cls._state[session_id]

    @classmethod
    def add_item(cls, session_id: str, product_id: str, qty: int = 1) -> CartResult:
        """Adds an item to the session's cart."""
        if qty <= 0:
            return CartResult(success=False, message="Quantity must be greater than 0.")
        product = get_product(product_id)
        if not product:
            return CartResult(success=False, message=f"Product {product_id} not found.")
        
        cart = cls._get_session_cart(session_id)
        
        # Check if item exists, update qty
        for item in cart:
            if item.product_id == product_id:
                if product.stock < item.quantity + qty:
                    return CartResult(success=False, message=f"Insufficient stock for {product.name}.")
                item.quantity += qty
                item.total_price_paise = item.quantity * item.unit_price_paise
                return CartResult(success=True, message=f"Updated {product.name} quantity to {item.quantity}.")

        # Add new item
        if product.stock < qty:
            return CartResult(success=False, message=f"Insufficient stock for {product.name}.")
            
        cart.append(CartItem(
            product_id=product.id,
            product_name=product.name,
            quantity=qty,
            unit_price_paise=product.price_paise,
            total_price_paise=product.price_paise * qty
        ))
        return CartResult(success=True, message=f"Added {qty} of {product.name} to cart.")

    @classmethod
    def add_custom_item(cls, session_id: str, name: str, price_paise: int, qty: int = 1, source_url: Optional[str] = None) -> CartResult:
        """Adds a web-sourced item (not from the local catalog) to the session's cart."""
        if qty <= 0:
            return CartResult(success=False, message="Quantity must be greater than 0.")
        if price_paise <= 0:
            return CartResult(success=False, message="price_paise must be greater than 0.")

        cart = cls._get_session_cart(session_id)
        item_id = f"custom_{uuid.uuid4().hex[:8]}"
        display_name = f"{name} ({source_url})" if source_url else name

        cart.append(CartItem(
            product_id=item_id,
            product_name=name,
            quantity=qty,
            unit_price_paise=price_paise,
            total_price_paise=price_paise * qty
        ))
        return CartResult(success=True, message=f"Added {qty} x {name} to cart at {price_paise / 100:.2f} INR each (product_id: {item_id}).")

    @classmethod
    def remove_item(cls, session_id: str, product_id: str) -> CartResult:
        """Removes an item from the session's cart."""
        cart = cls._get_session_cart(session_id)
        for i, item in enumerate(cart):
            if item.product_id == product_id:
                removed = cart.pop(i)
                return CartResult(success=True, message=f"Removed {removed.product_name} from cart.")
        return CartResult(success=False, message=f"Product {product_id} not in cart.")

    @classmethod
    def view_cart(cls, session_id: str) -> CartView:
        """Returns the current state of the cart."""
        cart = cls._get_session_cart(session_id)
        total = sum(item.total_price_paise for item in cart)
        count = sum(item.quantity for item in cart)
        return CartView(items=cart, total_paise=total, item_count=count)

    @classmethod
    def clear_cart(cls, session_id: str) -> CartResult:
        """Clears all items in the session's cart."""
        cls._state[session_id] = []
        return CartResult(success=True, message="Cart cleared.")

    @classmethod
    def get_total(cls, session_id: str) -> int:
        """Returns total in paise."""
        cart = cls._get_session_cart(session_id)
        return sum(item.total_price_paise for item in cart)