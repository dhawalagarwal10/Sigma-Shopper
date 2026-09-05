import json
from typing import Optional, Dict, Any, List
from merchant_core import catalog, cart, guardrails, audit, razorpay_client

# Initialize Razorpay client
rzp_client = razorpay_client.RazorpayClient()

def search_catalog(query: Optional[str] = None, category: Optional[str] = None, max_price: Optional[int] = None) -> dict:
    """Wraps catalog.search_products, no guardrails needed (read-only)."""
    products = catalog.search_products(query, category, max_price)
    return {"results": [p.model_dump() for p in products]}

def get_product_details(product_id: str) -> dict:
    """Wraps catalog.get_product + catalog.get_upsells, read-only."""
    product = catalog.get_product(product_id)
    if not product:
        return {"error": "Product not found"}
    upsells = catalog.get_upsells(product_id)
    return {
        "product": product.model_dump(),
        "upsells": [p.model_dump() for p in upsells]
    }

def add_to_cart(session_id: str, product_id: str, quantity: int = 1) -> dict:
    """Checks guardrails, calls cart.add_item, logs to audit."""
    product = catalog.get_product(product_id)
    if not product:
        return {"error": "Product not found"}
    
    proposed_cost = product.price_paise * quantity
    current_total = cart.Cart.get_total(session_id)
    proposed_total = current_total + proposed_cost
    
    spend_limit_check = guardrails.check_spend_limit(session_id, proposed_total)
    
    # Check max items rule (gate_action)
    action_gate = guardrails.gate_action(session_id, 'add_item', {'quantity': quantity})
    
    if not spend_limit_check.allowed:
        audit.log_event(
            session_id=session_id,
            action="add_to_cart",
            actor="GrowthAgent",
            details={"product_id": product_id, "quantity": quantity},
            reasoning=f"Attempted to add {quantity} of {product_id}",
            guardrail_result="blocked",
            outcome=spend_limit_check.reason
        )
        return {"error": spend_limit_check.reason}
        
    if not action_gate.allowed:
        audit.log_event(
            session_id=session_id,
            action="add_to_cart",
            actor="GrowthAgent",
            details={"product_id": product_id, "quantity": quantity},
            reasoning=f"Attempted to add {quantity} of {product_id}",
            guardrail_result="blocked",
            outcome=action_gate.reason
        )
        return {"error": action_gate.reason}
        
    result = cart.Cart.add_item(session_id, product_id, quantity)
    audit.log_event(
        session_id=session_id,
        action="add_to_cart",
        actor="GrowthAgent",
        details={"product_id": product_id, "quantity": quantity},
        reasoning=f"Added {quantity} of {product_id}",
        guardrail_result="allowed",
        outcome=result.message
    )
    return result.model_dump()

def view_cart(session_id: str) -> dict:
    """Wraps cart.view_cart, read-only."""
    return cart.Cart.view_cart(session_id).model_dump()

def remove_from_cart(session_id: str, product_id: str) -> dict:
    """Wraps cart.remove_item, logs to audit."""
    result = cart.Cart.remove_item(session_id, product_id)
    audit.log_event(
        session_id=session_id,
        action="remove_from_cart",
        actor="GrowthAgent",
        details={"product_id": product_id},
        reasoning=f"Removed {product_id}",
        guardrail_result="n/a",
        outcome=result.message
    )
    return result.model_dump()

def request_checkout(session_id: str) -> dict:
    """(a) get cart total, (b) check spend limit, (c) gate checkout action, (d) create mandate, (e) return mandate details."""
    cart_view = cart.Cart.view_cart(session_id)
    if cart_view.item_count == 0:
        return {"error": "Cart is empty"}
        
    spend_limit_check = guardrails.check_spend_limit(session_id, cart_view.total_paise)
    gate = guardrails.gate_action(session_id, "checkout", {"total_paise": cart_view.total_paise})
    
    if not spend_limit_check.allowed:
        audit.log_event(session_id, "request_checkout", "GrowthAgent", {"total_paise": cart_view.total_paise}, "Spend limit exceeded", "blocked", None, spend_limit_check.reason)
        return {"error": spend_limit_check.reason}
        
    items_list = [item.model_dump() for item in cart_view.items]
    mandate = guardrails.create_mandate(session_id, items_list, cart_view.total_paise, "User requested checkout")
    
    audit.log_event(
        session_id=session_id,
        action="request_checkout",
        actor="GrowthAgent",
        details={"total_paise": cart_view.total_paise},
        reasoning="Requested checkout for cart items",
        guardrail_result="requires_confirmation",
        mandate_id=mandate.mandate_id,
        outcome="Created mandate pending confirmation"
    )
    return {"status": "pending_confirmation", "mandate": mandate.model_dump(mode="json")}

def confirm_and_pay(session_id: str, mandate_id: str, customer_name: str = 'Test Customer', customer_email: str = 'test@example.com', customer_contact: str = '+919876543210') -> dict:
    """Confirms mandate, creates Razorpay order & payment link, logs."""
    mandate = guardrails.confirm_mandate(mandate_id)
    if not mandate:
        return {"error": "Invalid mandate_id"}
        
    order = rzp_client.create_order(mandate.total_paise, f"receipt_{mandate_id}")
    if "error" in order:
        return {"error": f"Failed to create order: {order['error']}"}
        
    pl = rzp_client.create_payment_link(
        amount_paise=mandate.total_paise,
        description="The Curated Gift Shop Order",
        customer_name=customer_name,
        customer_email=customer_email,
        customer_contact=customer_contact,
        reference_id=order.get("id")
    )
    
    if "error" in pl:
        return {"error": f"Failed to create payment link: {pl['error']}"}
        
    audit.log_event(
        session_id=session_id,
        action="confirm_and_pay",
        actor="GrowthAgent",
        details={"mandate_id": mandate_id, "payment_link_id": pl["id"]},
        reasoning="Confirmed mandate and generated payment link",
        guardrail_result="allowed",
        mandate_id=mandate_id,
        outcome=f"Payment link generated: {pl['short_url']}"
    )
    return {"payment_link_url": pl["short_url"], "payment_link_id": pl["id"]}

def check_payment_status(session_id: str, payment_link_id: str) -> dict:
    """Polls payment link status, logs result."""
    pl = rzp_client.fetch_payment_link(payment_link_id)
    if "error" in pl:
        return {"error": f"Failed to fetch payment link: {pl['error']}"}
        
    status = pl.get("status")
    audit.log_event(
        session_id=session_id,
        action="check_payment_status",
        actor="GrowthAgent",
        details={"payment_link_id": payment_link_id, "status": status},
        reasoning=f"Checking payment status for {payment_link_id}",
        guardrail_result="n/a",
        outcome=f"Status is {status}"
    )
    
    if status == "paid":
        return {"status": "success", "details": pl}
    elif status in ["expired", "cancelled", "failed"]:
        return {"status": "failure", "details": pl, "recovery_suggestions": "You can try again, use a different payment method, or cancel."}
    else:
        return {"status": "pending", "details": pl}

TOOL_DEFINITIONS = [
    {
        "name": "search_catalog",
        "description": "Searches the catalog for products based on query, category, or max price.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term to match against product name or description"},
                "category": {"type": "string", "description": "Category name to filter by"},
                "max_price": {"type": "integer", "description": "Maximum price in paise (1 INR = 100 paise)"}
            }
        }
    },
    {
        "name": "get_product_details",
        "description": "Gets details of a specific product and its upsell suggestions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "The ID of the product"}
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "add_to_cart",
        "description": "Adds a product to the user's cart.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The current session ID"},
                "product_id": {"type": "string", "description": "The ID of the product to add"},
                "quantity": {"type": "integer", "description": "Quantity to add"}
            },
            "required": ["session_id", "product_id"]
        }
    },
    {
        "name": "view_cart",
        "description": "Views the contents of the user's cart.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The current session ID"}
            },
            "required": ["session_id"]
        }
    },
    {
        "name": "remove_from_cart",
        "description": "Removes a product from the user's cart.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The current session ID"},
                "product_id": {"type": "string", "description": "The ID of the product to remove"}
            },
            "required": ["session_id", "product_id"]
        }
    },
    {
        "name": "request_checkout",
        "description": "Requests checkout for the current cart, returning mandate details for confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The current session ID"}
            },
            "required": ["session_id"]
        }
    },
    {
        "name": "confirm_and_pay",
        "description": "Confirms the checkout mandate and generates a payment link.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The current session ID"},
                "mandate_id": {"type": "string", "description": "The mandate ID returned by request_checkout"},
                "customer_name": {"type": "string", "description": "Customer's name"},
                "customer_email": {"type": "string", "description": "Customer's email"},
                "customer_contact": {"type": "string", "description": "Customer's phone number"}
            },
            "required": ["session_id", "mandate_id"]
        }
    },
    {
        "name": "check_payment_status",
        "description": "Checks the status of a payment link.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The current session ID"},
                "payment_link_id": {"type": "string", "description": "The payment link ID returned by confirm_and_pay"}
            },
            "required": ["session_id", "payment_link_id"]
        }
    }
]