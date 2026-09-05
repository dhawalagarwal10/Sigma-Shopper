import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import httpx
from anthropic import Anthropic

from config import ANTHROPIC_API_KEY

# The web fetch tool is currently a beta feature and requires this header.
# https://docs.claude.com/en/docs/agents-and-tools/tool-use/web-fetch-tool
WEB_FETCH_BETA_HEADER = "web-fetch-2025-09-10"

SYSTEM_PROMPT = """You are an autonomous AI shopping agent. A human has told you once, up front, exactly \
what they want to buy. You must find and purchase the real product yourself, with no further human input, \
using the tools available to you.

How to operate:
- Use web_search to find the product across real retailers (Amazon.in, the brand's own official site, Croma, \
or similar). Prefer Indian retail listings since the final payment will be in INR.
- Use web_fetch on the most promising result(s) to actually read the product page and confirm the real current \
price, not just a guess from a search snippet. Don't add anything to the cart based on an unconfirmed price.
- If multiple retailers carry it, pick one clear, well-matched listing (right product, right variant/color if \
the human specified one) rather than the cheapest-looking snippet you haven't verified.
- Once you have a confirmed product name, price (in INR, convert to paise: 1 INR = 100 paise), and source URL, \
call add_custom_item with that name, price_paise, and source_url.
- Guardrails are enforced on the server, not by you. If add_custom_item is rejected (for example a spend limit), \
do not retry the same call blindly. Tell the human plainly in your final summary that it exceeded the limit, or \
if there's a genuinely cheaper equivalent listing you already found, try that instead.
- Use view_cart to confirm the total before checkout.
- Call checkout only once you're confident you found the actual product the human asked for. Set max_amount_paise \
to a small buffer above the cart total from view_cart, and write a purpose string naming the exact product and source.
- Once checkout succeeds (you receive a payment_link_id and payment_link_url), stop calling tools. Give a short \
final summary: what you found, where, the confirmed price, and the total. Payment completion and status polling \
happen outside of you.
- If you cannot find and confirm a real listing for what was asked, say so plainly instead of guessing a price."""

TOOL_DEFINITIONS = [
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 6},
    {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 6},
    {
        "name": "add_custom_item",
        "description": "Adds a real, web-sourced product to the cart once its price has been confirmed by fetching the actual page. May be rejected by a server-side guardrail (e.g. spend limit).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Product name, including variant/color if relevant"},
                "price_paise": {"type": "integer", "description": "Confirmed price in paise (1 INR = 100 paise)"},
                "quantity": {"type": "integer", "description": "Quantity to add", "default": 1},
                "source_url": {"type": "string", "description": "The exact page the price was confirmed on"}
            },
            "required": ["name", "price_paise", "source_url"]
        }
    },
    {
        "name": "view_cart",
        "description": "Views current cart contents and the total in paise.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "remove_from_cart",
        "description": "Removes an item from the cart entirely, by the product_id returned when it was added.",
        "input_schema": {
            "type": "object",
            "properties": {"product_id": {"type": "string", "description": "The product ID to remove"}},
            "required": ["product_id"]
        }
    },
    {
        "name": "checkout",
        "description": "Declares intent and initiates checkout for the current cart. Creates a mandate and a real Razorpay test-mode payment link. Fails if intent max_amount_paise is below the cart total or the spend limit guardrail rejects it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_amount_paise": {"type": "integer", "description": "Your declared spending cap in paise; must be >= current cart total"},
                "purpose": {"type": "string", "description": "Plain-English reason naming the exact product and source"}
            },
            "required": ["max_amount_paise", "purpose"]
        }
    }
]

CLIENT_TOOL_NAMES = {"add_custom_item", "view_cart", "remove_from_cart", "checkout"}


class PathBTools:
    """Wraps Path B's HTTP endpoints. This is the only thing the agent is allowed to act through."""

    def __init__(self, http_client: httpx.Client, session_id: str):
        self.http = http_client
        self.session_id = session_id

    def add_custom_item(self, name: str, price_paise: int, source_url: str, quantity: int = 1):
        r = self.http.post(
            f"/cart/{self.session_id}/add_custom",
            json={"name": name, "price_paise": price_paise, "quantity": quantity, "source_url": source_url}
        )
        if r.status_code != 200:
            return {"error": r.text}
        return r.json()

    def view_cart(self):
        r = self.http.get(f"/cart/{self.session_id}")
        if r.status_code != 200:
            return {"error": r.text}
        return r.json()

    def remove_from_cart(self, product_id: str):
        r = self.http.delete(f"/cart/{self.session_id}/{product_id}")
        if r.status_code != 200:
            return {"error": r.text}
        return r.json()

    def checkout(self, max_amount_paise: int, purpose: str):
        payload = {
            "intent": {"max_amount_paise": max_amount_paise, "purpose": purpose},
            "customer_name": "AI Shopping Agent",
            "customer_email": "agent@example.com",
            "customer_contact": "9876543210"
        }
        r = self.http.post(f"/checkout/{self.session_id}", json=payload)
        if r.status_code != 200:
            return {"error": r.text}
        return r.json()


def run_agent_purchase(goal: str, tools: PathBTools):
    """Runs the Claude tool-use loop until it either checks out or gives up. Returns the checkout response dict, or None."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    history = [{"role": "user", "content": f"Find and buy this, for real: {goal}"}]
    checkout_result = None

    while True:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=history,
            tools=TOOL_DEFINITIONS,
            extra_headers={"anthropic-beta": WEB_FETCH_BETA_HEADER}
        )
        history.append({"role": "assistant", "content": response.content})

        client_tool_calls = [b for b in response.content if getattr(b, "type", None) == "tool_use" and b.name in CLIENT_TOOL_NAMES]

        if not client_tool_calls:
            final_text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
            if final_text:
                print(f"🤖 {final_text}")
            if response.stop_reason == "tool_use":
                # A server tool (web_search/web_fetch) ran and Claude wants to continue; loop again with no client action needed.
                continue
            return checkout_result

        tool_results = []
        for block in client_tool_calls:
            name = block.name
            args = block.input or {}
            print(f"🔧 {name}({', '.join(f'{k}={v}' for k, v in args.items())})")

            try:
                fn = getattr(tools, name)
                result = fn(**args)
            except Exception as e:
                result = {"error": str(e)}

            if name == "checkout" and isinstance(result, dict) and "error" not in result:
                checkout_result = result
                print(f"✅ Payment link created: {result.get('payment_link_url')}")
            elif isinstance(result, dict) and "error" in result:
                print(f"❌ {result['error']}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str)
            })

        history.append({"role": "user", "content": tool_results})


def poll_payment(http_client: httpx.Client, payment_link_id: str, attempts: int = 30, interval_secs: int = 10) -> bool:
    """Polls for up to attempts * interval_secs seconds (default: 5 minutes)."""
    print(f"⏳ Polling payment status for up to {attempts * interval_secs // 60} minutes...")
    for i in range(attempts):
        r = http_client.get(f"/status/{payment_link_id}")
        if r.status_code == 200:
            status = r.json().get("status")
            print(f"[{i + 1}/{attempts}] Status: {status}")
            if status == "paid":
                print("🎉 Payment successful!")
                return True
        time.sleep(interval_secs)
    print("⚠️ Payment timed out.")
    return False


def main():
    parser = argparse.ArgumentParser(description="Autonomous, web-search-driven AI Buyer against Path B")
    parser.add_argument("--goal", type=str, default=None, help="Skip the prompt and pass the goal directly (useful for scripted runs)")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="Base URL for the Path B API")
    parser.add_argument("--simulate-failure", action="store_true", help="Skip real payment completion to demo the failure/recovery path")
    args = parser.parse_args()

    goal = args.goal or input("🎯 What do you want me to buy? ").strip()
    if not goal:
        print("No goal given, exiting.")
        return

    session_id = f"ai_buyer_{uuid.uuid4().hex[:8]}"
    base_url = args.base_url.rstrip("/")

    print(f"🤖 Starting autonomous purchase session: {session_id}")
    print(f"🎯 Goal: {goal}")
    print("-" * 50)

    http_client = httpx.Client(base_url=base_url, timeout=30)
    tools = PathBTools(http_client, session_id)

    checkout_result = run_agent_purchase(goal, tools)

    success = False
    if checkout_result:
        payment_link_id = checkout_result["payment_link_id"]
        if args.simulate_failure:
            print("⏳ Simulating a failed/timed-out payment to demonstrate recovery...")
            time.sleep(2)
        else:
            success = poll_payment(http_client, payment_link_id)

        if not success:
            print("🔄 Payment did not complete. Demonstrating graceful recovery...")
            print("🧹 Clearing cart...")
            http_client.post(f"/cart/{session_id}/clear")
            print("🔁 Retrying purchase...")
            retry_result = run_agent_purchase(goal, tools)
            if retry_result:
                success = poll_payment(http_client, retry_result["payment_link_id"])
    else:
        print("⚠️ No checkout was completed for this goal.")

    print("-" * 50)
    print("📋 Fetching Audit Trail...")
    audit_resp = http_client.get(f"/audit/{session_id}")
    if audit_resp.status_code == 200:
        for log in audit_resp.json():
            print(f"[{log['timestamp']}] {log['action']} by {log['actor']} | Outcome: {log['outcome']} | Guardrail: {log['guardrail_result']}")
    else:
        print(f"❌ Failed to fetch audit logs: {audit_resp.text}")


if __name__ == "__main__":
    main()