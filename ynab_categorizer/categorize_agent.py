#!/usr/bin/env python3
"""
YNAB Transaction Categorization Agent
Fetches uncategorized transactions, uses AI to suggest categories, and sends batch to Slack
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import sys

# Configuration from environment variables
YNAB_API_TOKEN = os.getenv("YNAB_API_TOKEN")
YNAB_BUDGET_ID = os.getenv("YNAB_BUDGET_ID", "last-used")  # or specific budget ID
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#ynab-transactions")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")

# File to store processed transaction IDs and learning data
STATE_FILE = "/tmp/ynab_agent_state.json"


class YNABAgent:
    def __init__(self):
        self.ynab_headers = {
            "Authorization": f"Bearer {YNAB_API_TOKEN}",
            "Content-Type": "application/json"
        }
        self.state = self.load_state()
    
    def load_state(self) -> Dict:
        """Load agent state (processed transactions, learned patterns)"""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {
            "processed_transactions": [],
            "category_patterns": {}  # merchant -> category mappings learned from approvals
        }
    
    def save_state(self):
        """Save agent state"""
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def get_budget_categories(self) -> Dict[str, str]:
        """Fetch all budget categories from YNAB"""
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
    
    def get_uncategorized_transactions(self, days_back: int = 7) -> List[Dict]:
        """Fetch uncategorized transactions from YNAB"""
        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        url = f"https://api.ynab.com/v1/budgets/{YNAB_BUDGET_ID}/transactions"
        params = {"since_date": since_date}
        
        response = requests.get(url, headers=self.ynab_headers, params=params)
        response.raise_for_status()
        
        all_transactions = response.json()["data"]["transactions"]
        
        # Filter for uncategorized transactions we haven't processed yet
        uncategorized = []
        for txn in all_transactions:
            # Skip if already categorized or already processed
            if txn["category_id"] or txn["id"] in self.state["processed_transactions"]:
                continue
            # Skip transfers and split transactions (parent)
            if txn["transfer_account_id"] or txn.get("subtransactions"):
                continue
            # Skip if deleted or pending (not yet cleared)
            if txn["deleted"]:
                continue
            
            uncategorized.append(txn)
        
        return uncategorized
    
    def categorize_with_ai(self, transactions: List[Dict], categories: Dict[str, str]) -> List[Dict]:
        """Use Claude via OpenRouter to suggest categories for transactions"""
        if not transactions:
            return []
        
        # Build context with learned patterns
        learned_patterns = "\n".join([
            f"- {merchant}: {category}"
            for merchant, category in self.state["category_patterns"].items()
        ]) if self.state["category_patterns"] else "No learned patterns yet."
        
        # Prepare transaction list for AI
        txn_list = []
        for i, txn in enumerate(transactions, 1):
            amount = abs(txn["amount"]) / 1000  # YNAB uses milliunits
            txn_list.append(
                f"{i}. {txn['payee_name']} - ${amount:.2f} on {txn['date']}"
            )
        
        category_list = "\n".join([f"- {name}" for name in sorted(set(categories.values()))])
        txn_list_str = "\n".join(txn_list)
        
        prompt = f"""You are helping categorize personal finance transactions for YNAB (You Need A Budget).

Available categories:
{category_list}

Previously learned patterns from user approvals:
{learned_patterns}

Uncategorized transactions:
{txn_list_str}

For each transaction, suggest the most appropriate category based on:
1. The merchant/payee name
2. Previously learned patterns (highest priority)
3. Common transaction categorization logic
4. The transaction amount and date if relevant

Respond in JSON format with an array of objects, one per transaction:
[
  {{"transaction_number": 1, "category": "Category Name", "confidence": "high/medium/low"}},
  ...
]

Be concise and accurate. Only use categories from the available list."""

        # Call OpenRouter API
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/yourusername/ynab-agent",
                "X-Title": "YNAB Categorization Agent"
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 2000
            }
        )
        response.raise_for_status()
        
        # Parse AI response
        ai_response = response.json()["choices"][0]["message"]["content"]
        
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in ai_response:
            ai_response = ai_response.split("```json")[1].split("```")[0].strip()
        elif "```" in ai_response:
            ai_response = ai_response.split("```")[1].split("```")[0].strip()
        
        suggestions = json.loads(ai_response)
        
        # Match suggestions back to transactions
        for i, txn in enumerate(transactions):
            suggestion = suggestions[i]
            txn["suggested_category"] = suggestion["category"]
            txn["confidence"] = suggestion.get("confidence", "medium")
        
        return transactions
    
    def format_slack_message(self, transactions: List[Dict]) -> str:
        """Format transactions as a Slack message"""
        if not transactions:
            return "✅ No uncategorized transactions found!"
        
        message = f"📋 *Good morning! You have {len(transactions)} uncategorized transaction(s):*\n\n"
        
        for i, txn in enumerate(transactions, 1):
            amount = abs(txn["amount"]) / 1000
            emoji = self.get_category_emoji(txn["suggested_category"])
            confidence = txn.get("confidence", "medium")
            confidence_emoji = "🟢" if confidence == "high" else "🟡" if confidence == "medium" else "🔴"
            
            message += f"{i}. {emoji} *{txn['payee_name']}* - ${amount:.2f}\n"
            message += f"   → {txn['suggested_category']} {confidence_emoji}\n"
            message += f"   _{txn['date']}_\n\n"
        
        message += "\n*To approve:*\n"
        message += "• Reply `approve all` to categorize everything\n"
        message += "• Reply `approve 1,3,5` to approve specific numbers\n"
        message += "• Reply `1: Groceries` to change category for transaction 1\n"
        message += "• Reply `skip` to ignore for now\n"
        
        return message
    
    def get_category_emoji(self, category: str) -> str:
        """Return emoji for category"""
        emoji_map = {
            "groceries": "🛒", "grocery": "🛒",
            "dining": "🍽️", "restaurant": "🍽️", "food": "🍽️",
            "gas": "⛽", "fuel": "⛽",
            "coffee": "☕",
            "shopping": "🛍️",
            "entertainment": "🎬",
            "utilities": "💡",
            "rent": "🏠", "housing": "🏠", "mortgage": "🏠",
            "transportation": "🚗", "transit": "🚇",
            "health": "🏥", "medical": "🏥",
            "fitness": "💪", "gym": "💪",
            "subscriptions": "📱",
            "insurance": "🛡️",
            "gifts": "🎁",
            "travel": "✈️",
            "clothing": "👕",
            "personal": "👤",
            "pets": "🐾",
            "education": "📚",
            "income": "💰",
            "savings": "🏦",
        }
        
        category_lower = category.lower()
        for key, emoji in emoji_map.items():
            if key in category_lower:
                return emoji
        return "💳"
    
    def send_to_slack(self, message: str, transactions: List[Dict]) -> str:
        """Send message to Slack and store transaction data"""
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "channel": SLACK_CHANNEL,
                "text": message,
                "unfurl_links": False,
                "unfurl_media": False
            }
        )
        response.raise_for_status()
        result = response.json()
        
        if not result["ok"]:
            raise Exception(f"Slack API error: {result.get('error')}")
        
        # Store transaction data keyed by message timestamp
        ts = result["ts"]
        self.state[f"pending_{ts}"] = {
            "transactions": transactions,
            "timestamp": datetime.now().isoformat()
        }
        self.save_state()
        
        return ts
    
    def run(self):
        """Main agent execution"""
        print("🤖 YNAB Categorization Agent starting...")
        
        # Validate environment
        if not all([YNAB_API_TOKEN, SLACK_BOT_TOKEN, OPENROUTER_API_KEY]):
            print("❌ Missing required environment variables!")
            print(f"   YNAB_API_TOKEN: {'✓' if YNAB_API_TOKEN else '✗'}")
            print(f"   SLACK_BOT_TOKEN: {'✓' if SLACK_BOT_TOKEN else '✗'}")
            print(f"   OPENROUTER_API_KEY: {'✓' if OPENROUTER_API_KEY else '✗'}")
            sys.exit(1)
        
        try:
            # Fetch categories
            print("📂 Fetching YNAB categories...")
            categories = self.get_budget_categories()
            print(f"   Found {len(categories)} categories")
            
            # Fetch uncategorized transactions
            print("💳 Fetching uncategorized transactions...")
            transactions = self.get_uncategorized_transactions()
            print(f"   Found {len(transactions)} uncategorized transactions")
            
            if not transactions:
                print("✅ No work to do!")
                # Optionally send a "all clear" message to Slack
                return
            
            # Categorize with AI
            print("🧠 Categorizing with AI...")
            categorized = self.categorize_with_ai(transactions, categories)
            
            # Send to Slack
            print("💬 Sending to Slack...")
            message = self.format_slack_message(categorized)
            ts = self.send_to_slack(message, categorized)
            
            print(f"✅ Sent {len(categorized)} transactions to Slack (ts: {ts})")
            print("   Waiting for user approval...")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    agent = YNABAgent()
    agent.run()
