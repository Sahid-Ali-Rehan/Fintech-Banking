import os
import random
from flask import Flask, render_template, request, jsonify, session
from pymongo import MongoClient
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-secret-key")

# Retrieve connection string from environment
MONGO_URI = os.getenv("MONGO_URI")

try:
    client = MongoClient(MONGO_URI)
    db = client["metro_bank"]
    accounts_collection = db["accounts"]
    client.admin.command('ping')
    print("Connected securely to JP Morgan Chase core database systems.")
except Exception as e:
    print(f"Database linkage failed: {e}")

def safe_float(val):
    try:
        if not val or str(val).strip() == "":
            return 0.0
        return float(val)
    except ValueError:
        return 0.0

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    name = str(data.get('name', '')).strip()
    pin = str(data.get('pin', '')).strip()

    if not name or len(pin) != 4 or not pin.isdigit():
        return jsonify({"success": False, "error": "Invalid name string or 4-digit security PIN signature."}), 400

    while True:
        acc_num = str(random.randint(1000000000, 9999999999))
        if not accounts_collection.find_one({"account_number": acc_num}):
            break

    new_account = {
        "account_number": acc_num,
        "pin": pin,
        "name": name,
        "balance": 0.0,
        "fd_balance": 0.0,
        "fd_years_left": 0,
        "fd_rate": 0.06
    }
    
    accounts_collection.insert_one(new_account)
    return jsonify({"success": True, "account_number": acc_num, "name": name})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    acc_num = str(data.get('account_number', '')).strip()
    pin = str(data.get('pin', '')).strip()

    user = accounts_collection.find_one({"account_number": acc_num, "pin": pin})
    if user:
        session['user'] = acc_num
        user["_id"] = str(user["_id"])
        return jsonify({"success": True, "user": user})
    
    return jsonify({"success": False, "error": "Access denied. Invalid account credentials or authorization signature."}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({"success": True})

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Session unauthorized."}), 401
    
    user = accounts_collection.find_one({"account_number": session['user']})
    if user:
        user["_id"] = str(user["_id"])
        return jsonify({"success": True, "account_number": session['user'], "user": user})
    return jsonify({"success": False, "error": "Record resolution profile not found."}), 404

@app.route('/api/transaction', methods=['POST'])
def transaction():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Session unauthorized."}), 401
    
    acc_num = session['user']
    user = accounts_collection.find_one({"account_number": acc_num})
    if not user:
        return jsonify({"success": False, "error": "Target institutional ledger asset missing."}), 404

    data = request.json or {}
    action = data.get('action')
    amount = safe_float(data.get('amount', 0))

    if amount <= 0 and action in ['deposit', 'withdraw', 'invest']:
        return jsonify({"success": False, "error": "Transaction valuation metrics must exceed zero."}), 400

    if action == 'deposit':
        accounts_collection.update_one({"account_number": acc_num}, {"$inc": {"balance": amount}})
    
    elif action == 'withdraw':
        if amount > user["balance"]:
            return jsonify({"success": False, "error": "Insufficient cleared balance for ledger withdrawal request."}), 400
        accounts_collection.update_one({"account_number": acc_num}, {"$inc": {"balance": -amount}})
    
    elif action == 'invest':
        years = int(data.get('years', 1))
        if user["fd_balance"] > 0:
            return jsonify({"success": False, "error": "Active institutional fixed bond asset structure already detected."}), 400
        if amount > user["balance"]:
            return jsonify({"success": False, "error": "Insufficient liquid collateral resources for placement."}), 400
        
        accounts_collection.update_one(
            {"account_number": acc_num},
            {"$inc": {"balance": -amount}, "$set": {"fd_balance": amount, "fd_years_left": years}}
        )

    updated_user = accounts_collection.find_one({"account_number": acc_num})
    updated_user["_id"] = str(updated_user["_id"])
    return jsonify({"success": True, "user": updated_user})

@app.route('/api/timemachine', methods=['POST'])
def time_machine():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Session unauthorized."}), 401
    
    acc_num = session['user']
    user = accounts_collection.find_one({"account_number": acc_num})
    if not user:
        return jsonify({"success": False, "error": "Ledger asset configuration error."}), 404

    try:
        years_to_skip = int(request.json.get('years', 0))
    except (ValueError, TypeError):
        years_to_skip = 0
        
    if years_to_skip <= 0:
        return jsonify({"success": False, "error": "Temporal forward increment must be a positive scalar."}), 400

    receipt = {"matured": False, "msg": f"Fiscal progression model updated forward by {years_to_skip} intervals."}

    if user["fd_balance"] > 0:
        fd_balance = user["fd_balance"]
        fd_years_left = user["fd_years_left"]
        fd_rate = user["fd_rate"]
        balance = user["balance"]
        
        initial_principal = fd_balance

        # TRUE COMPOUND INTEREST LOOP (CAGR MECHANICS)
        for _ in range(years_to_skip):
            if fd_years_left > 0:
                # Interest earns money on the cumulative balance, not just the base principal
                interest = fd_balance * fd_rate
                fd_balance += interest  
                fd_years_left -= 1
                
                if fd_years_left == 0:
                    balance += fd_balance
                    total_growth = fd_balance - initial_principal
                    receipt = {
                        "matured": True,
                        "principal": f"${initial_principal:,.2f}",
                        "interest": f"${total_growth:,.2f}",
                        "total": f"${fd_balance:,.2f}"
                    }
                    fd_balance = 0.0
                    break
        
        if fd_balance > 0:
            receipt["msg"] = f"Fiscal interval updated. Accumulating compound yields. Horizon: {fd_years_left} cycles remaining."

        accounts_collection.update_one(
            {"account_number": acc_num},
            {"$set": {"balance": balance, "fd_balance": fd_balance, "fd_years_left": fd_years_left}}
        )

    updated_user = accounts_collection.find_one({"account_number": acc_num})
    updated_user["_id"] = str(updated_user["_id"])
    return jsonify({"success": True, "user": updated_user, "receipt": receipt})

if __name__ == '__main__':
    app.run(debug=True)