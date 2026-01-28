#!/usr/bin/env python3
"""
Quick test script to verify your API keys and connections
"""

import os
import requests
import sys

def test_ynab():
    """Test YNAB connection"""
    token = os.getenv("YNAB_API_TOKEN")
    if not token:
        print("❌ YNAB_API_TOKEN not set")
        return False
    
    try:
        response = requests.get(
            "https://api.ynab.com/v1/user",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code == 200:
            user_id = response.json()["data"]["user"]["id"]
            print(f"✅ YNAB connected! User ID: {user_id}")
            return True
        else:
            print(f"❌ YNAB error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ YNAB connection failed: {e}")
        return False


def test_slack():
    """Test Slack connection"""
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        print("❌ SLACK_BOT_TOKEN not set")
        return False
    
    try:
        response = requests.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {token}"}
        )
        result = response.json()
        if result.get("ok"):
            team = result.get("team")
            user = result.get("user")
            print(f"✅ Slack connected! Team: {team}, Bot: {user}")
            return True
        else:
            print(f"❌ Slack error: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Slack connection failed: {e}")
        return False


def test_openrouter():
    """Test OpenRouter connection"""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        print("❌ OPENROUTER_API_KEY not set")
        return False
    
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {key}"}
        )
        if response.status_code == 200:
            data = response.json()["data"]
            limit = data.get("limit", "unknown")
            usage = data.get("usage", 0)
            print(f"✅ OpenRouter connected! Limit: ${limit}, Used: ${usage}")
            return True
        else:
            print(f"❌ OpenRouter error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ OpenRouter connection failed: {e}")
        return False


def test_ynab_categories():
    """Test fetching YNAB categories"""
    token = os.getenv("YNAB_API_TOKEN")
    budget_id = os.getenv("YNAB_BUDGET_ID", "last-used")
    
    try:
        response = requests.get(
            f"https://api.ynab.com/v1/budgets/{budget_id}/categories",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code == 200:
            groups = response.json()["data"]["category_groups"]
            total = sum(len(g["categories"]) for g in groups)
            print(f"✅ Found {total} categories in your budget")
            return True
        else:
            print(f"❌ Could not fetch categories: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Category fetch failed: {e}")
        return False


if __name__ == "__main__":
    print("🧪 Testing YNAB Slack Agent Setup\n")
    
    results = []
    
    print("1️⃣ Testing YNAB connection...")
    results.append(test_ynab())
    print()
    
    print("2️⃣ Testing Slack connection...")
    results.append(test_slack())
    print()
    
    print("3️⃣ Testing OpenRouter connection...")
    results.append(test_openrouter())
    print()
    
    print("4️⃣ Testing YNAB categories...")
    results.append(test_ynab_categories())
    print()
    
    print("=" * 50)
    if all(results):
        print("🎉 All tests passed! You're ready to go!")
        print("\nNext steps:")
        print("1. Push this code to GitHub")
        print("2. Set up GitHub Secrets")
        print("3. Run the workflow manually to test")
        print("4. Check your Slack channel!")
        sys.exit(0)
    else:
        print("⚠️  Some tests failed. Please fix the issues above.")
        sys.exit(1)
