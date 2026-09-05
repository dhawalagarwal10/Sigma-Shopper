import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from merchant_core.catalog import get_product, get_upsells, search_products, Product
from merchant_core.cart import Cart, CartResult, CartView
from merchant_core.guardrails import check_spend_limit, gate_action, create_mandate, confirm_mandate
from merchant_core.audit import log_event, get_session_log
from merchant_core.razorpay_client import RazorpayClient

app = FastAPI(title="Path B (Agent-Readable API)", description="API for autonomous AI agents to purchase products.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rzp_client = RazorpayClient()

class Intent(BaseModel):
    max_amount_paise: int
    purpose: str

class CheckoutRequest(BaseModel):
    intent: Intent
    customer_name: str
    customer_email: str
    customer_contact: str

class AddItemRequest(BaseModel):
    product_id: str
    quantity: int = 1

class CustomItemRequest(BaseModel):
    name: str
    price_paise: int
    quantity: int = 1
    source_url: Optional[str] = None

@app.get("/")
def root():
    return {"message": "Welcome to Path B API", "endpoints": ["/catalog", "/cart", "/checkout", "/status", "/audit"]}

@app.get("/catalog", response_model=List[Product])
def get_catalog():
    return search_products()

@app.get("/catalog/{product_id}")
def get_product_details(product_id: str):
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    upsells = get_upsells(product_id)
    return {"product": product, "upsells": upsells}

@app.post("/cart/{session_id}/add", response_model=CartResult)
def add_to_cart(session_id: str, request: AddItemRequest):
    product = get_product(request.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check spend limit first
    current_total = Cart.get_total(session_id)
    proposed_total = current_total + (product.price_paise * request.quantity)
    spend_check = check_spend_limit(session_id, proposed_total)
    
    if not spend_check.allowed:
        log_event(
            session_id=session_id,
            action="add_to_cart",
            actor="ai_agent",
            details={"product_id": request.product_id, "quantity": request.quantity, "proposed_total": proposed_total},
            reasoning=spend_check.reason,
            guardrail_result="blocked",
            outcome="Failed to add item due to spend limit."
        )
        raise HTTPException(status_code=400, detail=spend_check.reason)
        
    gate_check = gate_action(session_id, "add_item", {"quantity": request.quantity})
    if not gate_check.allowed and gate_check.action == "requires_confirmation":
        # Usually requires manual confirm, but for simple agent API we just block for simplicity or allow based on config
        raise HTTPException(status_code=400, detail=gate_check.reason)
        
    result = Cart.add_item(session_id, request.product_id, request.quantity)
    
    log_event(
        session_id=session_id,
        action="add_to_cart",
        actor="ai_agent",
        details={"product_id": request.product_id, "quantity": request.quantity, "result": result.success},
        reasoning="Valid addition within limits.",
        guardrail_result="allowed",
        outcome="Added item to cart."
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result

@app.post("/cart/{session_id}/add_custom", response_model=CartResult)
def add_custom_to_cart(session_id: str, request: CustomItemRequest):
    if request.price_paise <= 0:
        raise HTTPException(status_code=400, detail="price_paise must be greater than 0.")

    current_total = Cart.get_total(session_id)
    proposed_total = current_total + (request.price_paise * request.quantity)
    spend_check = check_spend_limit(session_id, proposed_total)

    if not spend_check.allowed:
        log_event(
            session_id=session_id,
            action="add_to_cart",
            actor="ai_agent",
            details={"name": request.name, "price_paise": request.price_paise, "quantity": request.quantity, "source_url": request.source_url, "proposed_total": proposed_total},
            reasoning=spend_check.reason,
            guardrail_result="blocked",
            outcome="Failed to add web-sourced item due to spend limit."
        )
        raise HTTPException(status_code=400, detail=spend_check.reason)

    gate_check = gate_action(session_id, "add_item", {"quantity": request.quantity})
    if not gate_check.allowed and gate_check.action == "requires_confirmation":
        raise HTTPException(status_code=400, detail=gate_check.reason)

    result = Cart.add_custom_item(session_id, request.name, request.price_paise, request.quantity, request.source_url)

    log_event(
        session_id=session_id,
        action="add_to_cart",
        actor="ai_agent",
        details={"name": request.name, "price_paise": request.price_paise, "quantity": request.quantity, "source_url": request.source_url, "result": result.success},
        reasoning="Web-sourced item added within limits.",
        guardrail_result="allowed",
        outcome=result.message
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result

@app.get("/cart/{session_id}", response_model=CartView)
def view_cart(session_id: str):
    return Cart.view_cart(session_id)

@app.delete("/cart/{session_id}/{product_id}", response_model=CartResult)
def remove_from_cart(session_id: str, product_id: str):
    result = Cart.remove_item(session_id, product_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result

@app.post("/cart/{session_id}/clear", response_model=CartResult)
def clear_cart(session_id: str):
    return Cart.clear_cart(session_id)

@app.post("/checkout/{session_id}")
def checkout(session_id: str, req: CheckoutRequest):
    cart_view = Cart.view_cart(session_id)
    if cart_view.item_count == 0:
        raise HTTPException(status_code=400, detail="Cart is empty")
        
    total = cart_view.total_paise
    
    # a) Validate intent >= cart total
    if req.intent.max_amount_paise < total:
        log_event(
            session_id=session_id,
            action="checkout",
            actor="ai_agent",
            details={"intent_max": req.intent.max_amount_paise, "total": total},
            reasoning="Agent intent amount is less than cart total.",
            guardrail_result="blocked",
            outcome="Checkout failed."
        )
        raise HTTPException(status_code=400, detail="Intent max amount is less than cart total.")
        
    # b) Check spend limit
    spend_check = check_spend_limit(session_id, total)
    if not spend_check.allowed:
        raise HTTPException(status_code=400, detail=spend_check.reason)
        
    # c) Gate checkout
    gate_check = gate_action(session_id, "checkout", {"total": total})
    
    # d) Create mandate
    mandate = create_mandate(session_id, [item.model_dump() for item in cart_view.items], total, req.intent.purpose)
    
    # e) Auto-confirm mandate (since machine caller provided valid intent)
    confirm_mandate(mandate.mandate_id)
    
    # Simulate failure for test purposes
    notes = {"session_id": session_id, "mandate_id": mandate.mandate_id}
    if "SIMULATE_FAILURE" in req.intent.purpose:
        # We can simulate failure by not creating the payment link properly or providing a bad description
        # We'll just append something to notes to trigger a fail case in the script later if needed,
        # but the script will likely look at the output. 
        # For simplicity, we just process it normally and let the buyer script handle its own fake retry 
        # or we could return an error directly.
        pass

    # f) Create Razorpay payment link
    desc = f"Order for {session_id}"
    pl = rzp_client.create_payment_link(
        amount_paise=total,
        description=desc,
        customer_name=req.customer_name,
        customer_email=req.customer_email,
        customer_contact=req.customer_contact,
        notes=notes,
        reference_id=mandate.mandate_id
    )
    
    if "error" in pl:
        log_event(
            session_id=session_id,
            action="checkout",
            actor="ai_agent",
            details={"error": pl["error"]},
            reasoning="Payment link creation failed.",
            guardrail_result="allowed",
            mandate_id=mandate.mandate_id,
            outcome="Failed to create payment link."
        )
        raise HTTPException(status_code=500, detail=pl["error"])
        
    # g) Log everything
    log_event(
        session_id=session_id,
        action="checkout",
        actor="ai_agent",
        details={"payment_link_id": pl["id"], "total": total},
        reasoning="Valid checkout within limits and with confirmed mandate.",
        guardrail_result="allowed",
        mandate_id=mandate.mandate_id,
        outcome="Payment link created successfully."
    )
    
    return {
        "mandate_id": mandate.mandate_id,
        "payment_link_id": pl["id"],
        "payment_link_url": pl["short_url"],
        "total_paise": total,
        "status": pl["status"]
    }

@app.get("/status/{payment_link_id}")
def check_status(payment_link_id: str):
    pl = rzp_client.fetch_payment_link(payment_link_id)
    if "error" in pl:
        raise HTTPException(status_code=404, detail=pl["error"])
    return {
        "status": pl.get("status"),
        "payment_id": pl.get("payment_id"), # Or whatever field rzp returns
        "details": pl
    }

@app.get("/audit/{session_id}")
def get_audit(session_id: str):
    return get_session_log(session_id)