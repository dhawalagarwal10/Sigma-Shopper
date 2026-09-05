import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import time
from merchant_core.audit import get_all_logs, clear_logs

st.set_page_config(page_title="Audit Trail", page_icon="📋", layout="wide")

st.title("📋 Audit Trail — Razorpay Buildathon")
st.write("Live, append-only audit log tracking every action, guardrail check, and outcome.")

# Auto-refresh loop using a placeholder (or manual refresh)
col1, col2 = st.columns([1, 8])
with col1:
    if st.button("🔄 Refresh Now"):
        st.rerun()

logs = get_all_logs(limit=100)
st.metric("Total Events Logged", len(logs))

# Sidebar filters
st.sidebar.header("Filters")
if logs:
    all_sessions = list(set([log.session_id for log in logs]))
    all_actors = list(set([log.actor for log in logs]))
    all_results = list(set([log.guardrail_result for log in logs]))
    
    selected_session = st.sidebar.selectbox("Session ID", ["All"] + all_sessions)
    selected_actor = st.sidebar.selectbox("Actor", ["All"] + all_actors)
    selected_result = st.sidebar.selectbox("Guardrail Result", ["All"] + all_results)
    
    if st.sidebar.button("Clear All Logs", type="primary"):
        clear_logs()
        st.rerun()
        
    filtered_logs = logs
    if selected_session != "All":
        filtered_logs = [l for l in filtered_logs if l.session_id == selected_session]
    if selected_actor != "All":
        filtered_logs = [l for l in filtered_logs if l.actor == selected_actor]
    if selected_result != "All":
        filtered_logs = [l for l in filtered_logs if l.guardrail_result == selected_result]

    for log in reversed(filtered_logs):
        if log.guardrail_result == "passed":
            icon = "✅"
            color = "green"
        elif log.guardrail_result == "blocked":
            icon = "❌"
            color = "red"
        elif log.guardrail_result == "requires_confirmation":
            icon = "⚠️"
            color = "orange"
        else:
            icon = "ℹ️"
            color = "blue"
            
        with st.expander(f"{icon} {log.timestamp.strftime('%H:%M:%S')} | Session: {log.session_id[:8]}... | Action: {log.action}"):
            st.markdown(f"**Actor:** {log.actor}")
            st.markdown(f"**Reasoning:** {log.reasoning}")
            st.markdown(f"**Outcome:** {log.outcome}")
            if log.mandate_id:
                st.markdown(f"**Mandate ID:** `{log.mandate_id}`")
            st.json(log.details)
else:
    st.info("No audit logs found yet. Start interacting with the agent or API to generate logs.")

# Auto refresh every 5 seconds if running standalone
time.sleep(3)
st.rerun()
