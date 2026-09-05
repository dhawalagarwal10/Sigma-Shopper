import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anthropic import Anthropic
from config import ANTHROPIC_API_KEY
from path_a.tools import (
    TOOL_DEFINITIONS, search_catalog, get_product_details, add_to_cart,
    view_cart, remove_from_cart, request_checkout, confirm_and_pay, check_payment_status
)

class GrowthAgent:
    SYSTEM_PROMPT = """You are a helpful assistant for 'The Curated Gift Shop'.
You help customers find gifts, suggest relevant add-ons when natural (not pushy).
You can search the catalog, show product details, manage the cart, and process checkout.
IMPORTANT RULES:
- Never suggest add-ons that aren't in the upsell list.
- Only suggest add-ons once per conversation turn.
- Always summarize the cart before checkout.
- Always explain why you're suggesting something.
- Never proceed with checkout without explicit customer confirmation.
- When a payment fails, explain what happened clearly and offer options (retry, different method, or cancel)."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.history = []

    def chat(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})
        
        while True:
            try:
                response = self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1024,
                    system=self.SYSTEM_PROMPT,
                    messages=self.history,
                    tools=TOOL_DEFINITIONS
                )
                
                self.history.append({"role": "assistant", "content": response.content})
                
                if response.stop_reason == "tool_use":
                    for content_block in response.content:
                        if content_block.type == "tool_use":
                            tool_name = content_block.name
                            tool_args = content_block.input
                            
                            matching_tool = next((t for t in TOOL_DEFINITIONS if t["name"] == tool_name), {})
                            if "session_id" in matching_tool.get("input_schema", {}).get("properties", {}):
                                tool_args["session_id"] = self.session_id
                            
                            try:
                                if tool_name == "search_catalog":
                                    result = search_catalog(**tool_args)
                                elif tool_name == "get_product_details":
                                    result = get_product_details(**tool_args)
                                elif tool_name == "add_to_cart":
                                    result = add_to_cart(**tool_args)
                                elif tool_name == "view_cart":
                                    result = view_cart(**tool_args)
                                elif tool_name == "remove_from_cart":
                                    result = remove_from_cart(**tool_args)
                                elif tool_name == "request_checkout":
                                    result = request_checkout(**tool_args)
                                elif tool_name == "confirm_and_pay":
                                    result = confirm_and_pay(**tool_args)
                                elif tool_name == "check_payment_status":
                                    result = check_payment_status(**tool_args)
                                else:
                                    result = {"error": f"Unknown tool: {tool_name}"}
                            except Exception as e:
                                result = {"error": str(e)}
                            
                            self.history.append({
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": content_block.id,
                                        "content": json.dumps(result, default=str)
                                    }
                                ]
                            })
                else:
                    return response.content[0].text if response.content else ""
                    
            except Exception as e:
                return f"An error occurred: {str(e)}"