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
        """Fetch unapproved transactions from YNAB"""
        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        url = f"https://api.ynab.com/v1/budgets/{YNAB_BUDGET_ID}/transactions"
        params = {"since_date": since_date}
        
        response = requests.get(url, headers=self.ynab_headers, params=params)
        response.raise_for_status()
        
        all_transactions = response.json()["data"]["transactions"]
        
        # Filter for unapproved transactions (includes both uncategorized AND auto-categorized but not approved)
        unapproved = []
        for txn in all_transactions:
            # Skip if already approved or already processed
            if txn["approved"] or txn["id"] in self.state["processed_transactions"]:
                continue
            # Skip split transactions (parent) but NOT transfers
            if txn.get("subtransactions"):
                continue
            # Skip if deleted
            if txn["deleted"]:
                continue
            
            unapproved.append(txn)
        
        return unapproved
    
    def detect_transfer_pairs(self, transactions):
        """
        Detect matching transfer pairs and separate them from regular transactions.
        Returns: (transfer_pairs, non_transfer_transactions)
        """
        transfers = [txn for txn in transactions if txn.get("transfer_account_id")]
        non_transfers = [txn for txn in transactions if not txn.get("transfer_account_id")]
        
        # Group transfers by amount and date to find pairs
        transfer_pairs = []
        processed_ids = set()
        
        for i, txn1 in enumerate(transfers):
            if txn1["id"] in processed_ids:
                continue
                
            amount1 = txn1["amount"]
            date1 = txn1["date"]
            account1 = txn1["account_id"]
            transfer_account1 = txn1.get("transfer_account_id")
            
            # Look for matching transfer (opposite amount, same date, accounts match)
            for txn2 in transfers[i+1:]:
                if txn2["id"] in processed_ids:
                    continue
                
                amount2 = txn2["amount"]
                date2 = txn2["date"]
                account2 = txn2["account_id"]
                transfer_account2 = txn2.get("transfer_account_id")
                
                # Check if they're a matching pair
                if (date1 == date2 and 
                    amount1 == -amount2 and
                    account1 == transfer_account2 and
                    account2 == transfer_account1):
                    
                    transfer_pairs.append((txn1, txn2))
                    processed_ids.add(txn1["id"])
                    processed_ids.add(txn2["id"])
                    break
        
        # Any unmatched transfers go back into non_transfers
        unmatched_transfers = [txn for txn in transfers if txn["id"] not in processed_ids]
        non_transfers.extend(unmatched_transfers)
        
        return transfer_pairs, non_transfers

    
    def detect_transfer_pairs(self, transactions: List[Dict]) -> tuple[List[tuple], List[Dict]]:
        """
        Detect matching transfer pairs and separate them from regular transactions.
        Returns: (transfer_pairs, non_transfer_transactions)
        """
        transfers = [txn for txn in transactions if txn.get("transfer_account_id")]
        non_transfers = [txn for txn in transactions if not txn.get("transfer_account_id")]
        
        # Group transfers by amount and date to find pairs
        transfer_pairs = []
        processed_ids = set()
        
        for i, txn1 in enumerate(transfers):
            if txn1["id"] in processed_ids:
                continue
                
            amount1 = txn1["amount"]
            date1 = txn1["date"]
            account1 = txn1["account_id"]
            transfer_account1 = txn1.get("transfer_account_id")
            
            # Look for matching transfer (opposite amount, same date, accounts match)
            for txn2 in transfers[i+1:]:
                if txn2["id"] in processed_ids:
                    continue
                
                amount2 = txn2["amount"]
                date2 = txn2["date"]
                account2 = txn2["account_id"]
                transfer_account2 = txn2.get("transfer_account_id")
                
                # Check if they're a matching pair
                if (date1 == date2 and 
                    amount1 == -amount2 and
                    account1 == transfer_account2 and
                    account2 == transfer_account1):
                    
                    transfer_pairs.append((txn1, txn2))
                    processed_ids.add(txn1["id"])
                    processed_ids.add(txn2["id"])
                    break
        
        # Any unmatched transfers go back into non_transfers
        unmatched_transfers = [txn for txn in transfers if txn["id"] not in processed_ids]
        non_transfers.extend(unmatched_transfers)
        
        return transfer_pairs, non_transfers
    
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
            existing_cat = None
            if txn.get("category_id"):
                existing_cat = categories.get(txn["category_id"], "Unknown")
            
            txn_str = f"{i}. {txn['payee_name']} - ${amount:.2f} on {txn['date']}"
            if existing_cat:
                txn_str += f" (YNAB suggested: {existing_cat})"
            txn_list.append(txn_str)
        
        category_list = "\n".join([f"- {name}" for name in sorted(set(categories.values()))])
        txn_list_str = "\n".join(txn_list)
        
        prompt = f"""You are helping categorize personal finance transactions for YNAB (You Need A Budget).

Available categories:
{category_list}

Previously learned patterns from user approvals:
{learned_patterns}

Unapproved transactions (some may have YNAB's auto-suggestion):
{txn_list_str}

For each transaction, suggest the most appropriate category based on:
1. Previously learned patterns (highest priority - the user has approved these before)
2. YNAB's existing suggestion if shown (consider it but you can override if learned patterns say otherwise)
3. The merchant/payee name
4. Common transaction categorization logic
5. The transaction amount and date if relevant

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
    
    def send_to_slack(self, message: str, transactions: List[Dict], transfer_pairs=None) -> str:
        """Send message to Slack with interactive buttons and dropdowns"""
        
        # Get all category names for the dropdown
        categories = self.get_budget_categories()
        category_options = [
            {"text": {"type": "plain_text", "text": cat}, "value": cat}
            for cat in sorted(set(categories.values()))
        ]
        
        if transfer_pairs is None:
            transfer_pairs = []
        
        total_count = len(transactions) + len(transfer_pairs) * 2
        
        # Build interactive blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📋 Good morning! You have {total_count} unapproved transaction(s):",
                    "emoji": True
                }
            }
        ]
        
        # Add transfer pairs section if any exist
        if transfer_pairs:
            # Get account names
            accounts_url = f"https://api.ynab.com/v1/budgets/{YNAB_BUDGET_ID}/accounts"
            accounts_response = requests.get(accounts_url, headers=self.ynab_headers)
            accounts_response.raise_for_status()
            accounts = {acc["id"]: acc["name"] for acc in accounts_response.json()["data"]["accounts"]}
            
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🔄 Found {len(transfer_pairs)} matching transfer pair(s):*"
                }
            })
            
            # List each transfer pair
            transfer_list = []
            for txn1, txn2 in transfer_pairs:
                amount = abs(txn1["amount"]) / 1000
                account1 = accounts.get(txn1["account_id"], "Unknown")
                account2 = accounts.get(txn2["account_id"], "Unknown")
                transfer_list.append(f"• ${amount:.2f} - {account1} ↔ {account2}")
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(transfer_list)
                }
            })
            
            # Add "Approve All Transfers" button
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✓ Approve All Transfers",
                            "emoji": True
                        },
                        "value": "approve_all_transfers",
                        "action_id": "approve_all_transfers",
                        "style": "primary"
                    }
                ]
            })
        
        # Regular transactions section
        if transactions:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*💳 {len(transactions)} regular transaction(s) to categorize:*"
                }
            })
            blocks.append({"type": "divider"})
        else:
            blocks.append({"type": "divider"})
        
        # Add a section for each transaction with buttons
        for i, txn in enumerate(transactions, 1):
            amount = abs(txn["amount"]) / 1000
            emoji = self.get_category_emoji(txn["suggested_category"])
            confidence = txn.get("confidence", "medium")
            confidence_emoji = "🟢" if confidence == "high" else "🟡" if confidence == "medium" else "🔴"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{i}. {emoji} {txn['payee_name']}* - ${amount:.2f}\n→ {txn['suggested_category']} {confidence_emoji}\n_{txn['date']}_"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✓ Approve",
                        "emoji": True
                    },
                    "value": f"approve_{i}",
                    "action_id": f"approve_transaction_{i}",
                    "style": "primary"
                }
            })
            
            # Add category dropdown below
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": " "
                },
                "accessory": {
                    "type": "static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Change category",
                        "emoji": True
                    },
                    "options": category_options,
                    "action_id": f"change_category_{i}"
                }
            })
            
            blocks.append({"type": "divider"})
        
        # Add bulk action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✓ Approve All Regular",
                        "emoji": True
                    },
                    "value": "approve_all",
                    "action_id": "approve_all_transactions",
                    "style": "primary"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Skip",
                        "emoji": True
                    },
                    "value": "skip",
                    "action_id": "skip_transactions"
                }
            ]
        })
        
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "channel": SLACK_CHANNEL,
                "text": f"You have {len(transactions)} uncategorized transactions",  # Fallback text
                "blocks": blocks,
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
            "transfer_pairs": transfer_pairs if transfer_pairs else [],
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
            print("💳 Fetching unapproved transactions...")
            transactions = self.get_uncategorized_transactions()
            print(f"   Found {len(transactions)} unapproved transactions")
            
            if not transactions:
                print("✅ No work to do!")
                # Optionally send a "all clear" message to Slack
                return
            
            # Detect transfer pairs
            print("🔄 Detecting transfer pairs...")
            transfer_pairs, non_transfer_txns = self.detect_transfer_pairs(transactions)
            print(f"   Found {len(transfer_pairs)} transfer pairs, {len(non_transfer_txns)} regular transactions")
            
            # Categorize non-transfer transactions with AI
            if non_transfer_txns:
                print("🧠 Categorizing with AI...")
                categorized = self.categorize_with_ai(non_transfer_txns, categories)
            else:
                categorized = []
            
            # Send to Slack
            print("💬 Sending to Slack...")
            ts = self.send_to_slack("", categorized, transfer_pairs)  # Message built in send_to_slack now
            
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
