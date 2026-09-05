# Razorpay Buildathon — Track 01: AI Growth & Agentic Commerce

This project is a unified merchant system featuring two distinct checkout flows (front doors) built on a shared, robust merchant core. It fully implements the Razorpay test-mode integration, spend limits, action gating, and an append-only audit trail as required by the Buildathon guidelines.

## Features

- **Shared Merchant Core (`merchant_core/`)**: Houses the product catalog, cart management, Razorpay SDK wrappers, guardrails (spend limits, checkout gating), and an append-only JSONL audit log.
- **Path A — Growth Agent (`path_a/`)**: A conversational AI (powered by Claude 3.5 Sonnet) wrapped in a Streamlit chat UI. It acts as a helpful shop assistant, suggests logical add-ons, and completes purchases securely inside the chat.
- **Path B — Agent-Readable API (`path_b/`)**: A FastAPI application providing structured `/catalog`, `/cart`, and `/checkout` endpoints. It enables external AI systems to securely navigate and purchase products programmatically, verifying intent mandates automatically.
- **AI Buyer Script (`ai_buyer/`)**: A standalone script that acts as an autonomous agent interacting with Path B to demonstrate machine-to-machine checkout. Includes a failure simulation mode to demonstrate resilient recovery.
- **Audit Dashboard (`dashboard/`)**: A live Streamlit dashboard to trace every action, reasoning, and guardrail evaluation across the platform.

## Setup Instructions

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables**
   Create a `.env` file in the root directory (using `.env.example` as a template):
   ```
   RAZORPAY_KEY_ID=rzp_test_your_razorpay_key
   RAZORPAY_KEY_SECRET=your_razorpay_secret
   ANTHROPIC_API_KEY=sk-ant-your_anthropic_key
   ```
   *Note: Ensure your Razorpay account is in Test Mode.*

## Running the Project

### 1. Run the Human-Facing Growth Agent (Path A)
Launch the interactive Streamlit chat UI:
```bash
python -m streamlit run path_a/chat_app.py
```
Open your browser to the URL provided (usually `http://localhost:8501`). Chat with the bot, build a cart, and complete a test purchase!

### 2. Run the Agent-Readable API (Path B)
Start the FastAPI server:
```bash
python -m uvicorn path_b.api:app --reload --port 8000
```
View the interactive API docs at `http://localhost:8000/docs`.

### 3. Run the Demo AI Buyer (Against Path B)
With the FastAPI server running, open a new terminal and run:
```bash
python -m ai_buyer.buyer
```
**To test the gracefully handled failure case (Phase 6):**
```bash
python -m ai_buyer.buyer --simulate-failure
```

### 4. View the Live Audit Trail
Launch the Streamlit dashboard in a separate terminal:
```bash
python -m streamlit run dashboard/audit_viewer.py
```
This shows a real-time, color-coded log of every action (human or AI), the reasoning behind it, and whether it passed the guardrails.

## Failure Simulation & Guardrails (The Bar)
- **Bounded:** A hard spend limit is enforced (`MAX_SESSION_SPEND`). Try adding too many items to the cart in Path A.
- **Gated:** Checkout always requires explicit mandate generation and confirmation.
- **Explainable:** The `dashboard` displays the explicit reasoning for every agent action.
- **One Failure Handled Gracefully:** Running `python -m ai_buyer.buyer --simulate-failure` forces a Razorpay failure utilizing `failure@razorpay` as the VPA. The system gracefully catches this, logs the failure, and attempts a recovery action.
