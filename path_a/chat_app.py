import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import uuid
from path_a.agent import GrowthAgent
from merchant_core.cart import Cart
from merchant_core.audit import get_session_log

st.set_page_config(page_title="The Curated Gift Shop", page_icon="🎁", layout="wide")

st.title("🎁 The Curated Gift Shop — AI Assistant")

if "session_id" not in st.session_state:
    st.session_state.session_id = f"chat_{uuid.uuid4().hex[:8]}"
    st.session_state.agent = GrowthAgent(st.session_state.session_id)
    st.session_state.messages = []

# Sidebar for Context & Audit
with st.sidebar:
    st.header("Session Details")
    st.write(f"**Session ID:** `{st.session_state.session_id}`")
    
    st.subheader("🛒 Current Cart")
    cart_view = Cart.view_cart(st.session_state.session_id)
    if cart_view.item_count == 0:
        st.write("Cart is empty.")
    else:
        for item in cart_view.items:
            st.write(f"- {item.quantity}x {item.product_name} (₹{item.total_price_paise/100:.2f})")
        st.write(f"**Total: ₹{cart_view.total_paise/100:.2f}**")
        
    with st.expander("View Audit Log"):
        logs = get_session_log(st.session_state.session_id)
        if not logs:
            st.write("No actions logged yet.")
        else:
            for log in reversed(logs[-10:]):
                status = "✅" if log.guardrail_result == "passed" else "❌" if log.guardrail_result == "blocked" else "ℹ️"
                st.caption(f"{status} **{log.action}**")
                st.caption(f"Reason: {log.reasoning}")
                st.divider()

    if st.button("Reset Session"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# Main Chat Interface
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("How can I help you find the perfect gift?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = st.session_state.agent.chat(prompt)
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()
