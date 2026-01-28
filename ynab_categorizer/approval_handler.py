#!/usr/bin/env python3
"""
YNAB Slack Approval Handler
Processes user responses from Slack and updates YNAB transactions
"""

import os
import json
import requests
import re
from typing import Dict, List
from flask import Flask, request, jsonify

# Configuration
YNAB_API_TOKEN = os.getenv("YNAB_API_TOKEN")
YNAB_BUDGET_ID = os.getenv("YNAB_BUDGET_ID", "last-used")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
STATE_FILE = "/tmp/ynab_agent_state.json"

app = Flask(__name__)


class ApprovalHandler:
    def __init__(self):
        self.ynab_headers = {
            "Authorization": f"Bearer {YNAB_API_TOKEN}",
            "Content-Type": "application/json"
        }
        self.state = self.load_state()
        self.categories = self.get_categories()
        self.category_name_to_id = {v: k for k, v in self.categories.items()}
    
    def load_state(self) -> Dict:
        """Load agent state"""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {"processed_transactions": [], "category_patterns": {}}
    
    def save_state(self):
        """Save agent state"""
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def get_categories(self) -> Dict[str, str]:
        """Fetch categories from YNAB"""
        url = f"https://api.ynab.com/v1/budgets/{YNAB_BUDGET_ID}/categories"
        response = requests.get(url, headers=self.ynab_headers)
        response.raise_for_status()
        
        categories = {}
        for group in response.json()["data"]["category_groups"]:
            if group["name"] in ["Internal Master Category", "Hidden Categories"]:
                continue
            for cat in group["categories"]:
                if not cat["hidden"] and not cat["deleted"]:
                    categories[cat["id"]] = cat["name"]
        return categories
    
    def find_pending_transactions(self, thread_ts: str) -> List[Dict]:
        """Find pending transactions by thread timestamp"""
        pending_key = f"pending_{thread_ts}"
        if pending_key in self.state:
            return self.state[pending_key]["transactions"]
        return None
    
    def update_ynab_transaction(self, transaction_id: str, category_name: str) -> bool:
        """Update a transaction's category in YNAB"""
        category_id = self.category_name_to_id.get(category_name)
        if not category_id:
            return False
        
        url = f"https://api.ynab.com/v1/budgets/{YNAB_BUDGET_ID}/transactions/{transaction_id}"
        response = requests.patch(
            url,
            headers=self.ynab_headers,
            json={"transaction": {"category_id": category_id}}
        )
        return response.status_code == 200
    
    def learn_pattern(self, payee_name: str, category: str):
        """Learn a merchant -> category pattern"""
        # Normalize payee name
        normalized = payee_name.lower().strip()
        self.state["category_patterns"][normalized] = category
        self.save_state()
    
    def process_approval(self, text: str, thread_ts: str, channel: str) -> str:
        """Process user approval message"""
        transactions = self.find_pending_transactions(thread_ts)
        
        if not transactions:
            return "❌ Could not find pending transactions. They may have already been processed."
        
        text_lower = text.lower().strip()
        
        # Handle "approve all"
        if "approve all" in text_lower:
            return self.approve_all(transactions, thread_ts, channel)
        
        # Handle "approve 1,3,5"
        if text_lower.startswith("approve "):
            numbers = re.findall(r'\d+', text)
            return self.approve_specific(transactions, numbers, thread_ts, channel)
        
        # Handle "1: Groceries" (change category)
        if ":" in text:
            match = re.match(r'(\d+):\s*(.+)', text.strip())
            if match:
                txn_num = int(match.group(1))
                new_category = match.group(2).strip()
                return self.change_category(transactions, txn_num, new_category, thread_ts, channel)
        
        # Handle "skip"
        if text_lower == "skip":
            return "👍 Skipped. I'll check again tomorrow."
        
        return "🤔 I didn't understand that. Try:\n• `approve all`\n• `approve 1,3,5`\n• `1: Category Name`\n• `skip`"
    
    def approve_all(self, transactions: List[Dict], thread_ts: str, channel: str) -> str:
        """Approve all suggested categorizations"""
        results = []
        for i, txn in enumerate(transactions, 1):
            category = txn["suggested_category"]
            success = self.update_ynab_transaction(txn["id"], category)
            
            if success:
                # Learn this pattern
                self.learn_pattern(txn["payee_name"], category)
                # Mark as processed
                self.state["processed_transactions"].append(txn["id"])
                results.append(f"✅ {i}. {txn['payee_name']} → {category}")
            else:
                results.append(f"❌ {i}. {txn['payee_name']} (failed)")
        
        # Clean up pending transactions
        self.state.pop(f"pending_{thread_ts}", None)
        self.save_state()
        
        success_count = sum(1 for r in results if r.startswith("✅"))
        
        message = f"*Updated {success_count}/{len(transactions)} transactions:*\n\n" + "\n".join(results)
        return message
    
    def approve_specific(self, transactions: List[Dict], numbers: List[str], thread_ts: str, channel: str) -> str:
        """Approve specific transaction numbers"""
        results = []
        approved_ids = []
        
        for num_str in numbers:
            num = int(num_str)
            if num < 1 or num > len(transactions):
                results.append(f"❌ {num}. Invalid transaction number")
                continue
            
            txn = transactions[num - 1]
            category = txn["suggested_category"]
            success = self.update_ynab_transaction(txn["id"], category)
            
            if success:
                self.learn_pattern(txn["payee_name"], category)
                approved_ids.append(txn["id"])
                results.append(f"✅ {num}. {txn['payee_name']} → {category}")
            else:
                results.append(f"❌ {num}. {txn['payee_name']} (failed)")
        
        # Mark approved as processed
        self.state["processed_transactions"].extend(approved_ids)
        
        # Keep unapproved transactions in pending
        remaining = [txn for txn in transactions if txn["id"] not in approved_ids]
        if remaining:
            self.state[f"pending_{thread_ts}"]["transactions"] = remaining
        else:
            self.state.pop(f"pending_{thread_ts}", None)
        
        self.save_state()
        
        message = f"*Approved {len(approved_ids)} transaction(s):*\n\n" + "\n".join(results)
        if remaining:
            message += f"\n\n_{len(remaining)} transaction(s) still pending approval._"
        
        return message
    
    def change_category(self, transactions: List[Dict], txn_num: int, new_category: str, thread_ts: str, channel: str) -> str:
        """Change category for a specific transaction"""
        if txn_num < 1 or txn_num > len(transactions):
            return f"❌ Invalid transaction number: {txn_num}"
        
        txn = transactions[txn_num - 1]
        
        # Find matching category (case-insensitive)
        matched_category = None
        for cat_name in self.category_name_to_id.keys():
            if cat_name.lower() == new_category.lower():
                matched_category = cat_name
                break
        
        if not matched_category:
            # Try partial match
            for cat_name in self.category_name_to_id.keys():
                if new_category.lower() in cat_name.lower():
                    matched_category = cat_name
                    break
        
        if not matched_category:
            available = ", ".join(sorted(self.category_name_to_id.keys())[:10])
            return f"❌ Category '{new_category}' not found. Available categories include: {available}..."
        
        success = self.update_ynab_transaction(txn["id"], matched_category)
        
        if success:
            self.learn_pattern(txn["payee_name"], matched_category)
            self.state["processed_transactions"].append(txn["id"])
            
            # Remove from pending
            remaining = [t for t in transactions if t["id"] != txn["id"]]
            if remaining:
                self.state[f"pending_{thread_ts}"]["transactions"] = remaining
            else:
                self.state.pop(f"pending_{thread_ts}", None)
            
            self.save_state()
            
            message = f"✅ Updated: {txn['payee_name']} → {matched_category}"
            if remaining:
                message += f"\n\n_{len(remaining)} transaction(s) still pending._"
            return message
        else:
            return f"❌ Failed to update {txn['payee_name']}"


handler = ApprovalHandler()


@app.route("/slack/events", methods=["POST"])
def slack_events():
    """Handle Slack events (messages)"""
    data = request.json
    
    # Handle URL verification challenge
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})
    
    # Handle app mentions and messages
    if data.get("type") == "event_callback":
        event = data.get("event", {})
        
        # Ignore bot messages
        if event.get("bot_id"):
            return jsonify({"ok": True})
        
        # Process message
        if event.get("type") == "message":
            text = event.get("text", "")
            channel = event.get("channel")
            thread_ts = event.get("thread_ts") or event.get("ts")
            
            # Process the approval
            response = handler.process_approval(text, thread_ts, channel)
            
            # Send response to Slack
            requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "channel": channel,
                    "thread_ts": thread_ts,
                    "text": response
                }
            )
    
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
