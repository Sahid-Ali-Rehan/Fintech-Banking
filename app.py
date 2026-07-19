import os
import random
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-secret-key")

MONGO_URI = os.getenv("MONGO_URI")

try:
    client = MongoClient(MONGO_URI)
    db = client["metro_bank"]
    accounts_collection = db["accounts"]
    transactions_collection = db["transactions"]  # Permanently log every activity
    client.admin.command('ping')
    print("Securely linked to Prestige DB Systems.")
except Exception as e:
    print(f"Database connection error: {e}")

def safe_float(val):
    try:
        if not val or str(val).strip() == "":
            return 0.0
        return float(val)
    except ValueError:
        return 0.0

def generate_receipt_ref():
    return f"TXN-{uuid.uuid4().hex[:12].upper()}"

def record_transaction(account_number, ref_id, description, amount_value):
    """Safely saves transactional ledger history records in database."""
    try:
        transactions_collection.insert_one({
            "account_number": account_number,
            "reference_id": ref_id,
            "description": description,
            "amount_value": float(amount_value),
            "amount": f"${abs(float(amount_value)):,.2f}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        print(f"Ledger logging failed: {e}")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    name = str(data.get('name', '')).strip()
    pin = str(data.get('pin', '')).strip()

    if not name or len(pin) != 4 or not pin.isdigit():
        return jsonify({"success": False, "error": "Invalid client registry configurations."}), 400

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
        "fd_rate": 0.06,
        "loan_balance": 0.0,
        "loan_interest_rate": 0.07
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
    
    return jsonify({"success": False, "error": "System Authentication Failed."}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({"success": True})

@app.route('/api/history', methods=['GET'])
def transaction_history():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Unauthorized session context."}), 401
    
    acc_num = session['user']
    tx_cursor = transactions_collection.find({"account_number": acc_num}).sort("_id", -1)
    history = []
    for tx in tx_cursor:
        history.append({
            "reference_id": tx["reference_id"],
            "description": tx["description"],
            "amount_value": tx["amount_value"],
            "amount": tx["amount"],
            "timestamp": tx["timestamp"]
        })
    return jsonify({"success": True, "history": history})

@app.route('/api/transaction', methods=['POST'])
def transaction():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Unauthorized session context."}), 401
    
    acc_num = session['user']
    user = accounts_collection.find_one({"account_number": acc_num})
    if not user:
        return jsonify({"success": False, "error": "Account context missing."}), 404

    data = request.json or {}
    action = data.get('action')
    amount = safe_float(data.get('amount', 0))
    receipt = {}

    if amount <= 0 and action in ['deposit', 'withdraw', 'invest']:
        return jsonify({"success": False, "error": "Transaction valuation metrics must exceed zero."}), 400

    if action == 'deposit':
        accounts_collection.update_one({"account_number": acc_num}, {"$inc": {"balance": amount}})
        ref_id = generate_receipt_ref()
        record_transaction(acc_num, ref_id, "Liquid Collateral Deposit", amount)
        receipt = {
            "reference_id": ref_id,
            "status": "APPROVED",
            "meta": {
                "transaction_type": "Credit Entry (Deposit)",
                "amount": f"${amount:,.2f}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "allocated_ledger": "Liquid Assets Balance",
            }
        }
    
    elif action == 'withdraw':
        if amount > user["balance"]:
            return jsonify({"success": False, "error": "Insufficient liquid capital cleared."}), 400
        accounts_collection.update_one({"account_number": acc_num}, {"$inc": {"balance": -amount}})
        ref_id = generate_receipt_ref()
        record_transaction(acc_num, ref_id, "Liquid Collateral Withdrawal", -amount)
        receipt = {
            "reference_id": ref_id,
            "status": "APPROVED",
            "meta": {
                "transaction_type": "Debit Entry (Withdrawal)",
                "amount": f"${amount:,.2f}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cleared_by": "System Cashout Desk"
            }
        }
    
    elif action == 'invest':
        try:
            years = int(data.get('years', 0))
        except (ValueError, TypeError):
            years = 0

        if years <= 0:
            return jsonify({"success": False, "error": "Please define structural years of at least 1 cycle."}), 400
        if user.get("fd_balance", 0.0) > 0:
            return jsonify({"success": False, "error": "An active fixed horizon configuration exists."}), 400
        if amount > user["balance"]:
            return jsonify({"success": False, "error": "Insufficient liquid collateral resources."}), 400
        
        accounts_collection.update_one(
            {"account_number": acc_num},
            {"$inc": {"balance": -amount}, "$set": {"fd_balance": amount, "fd_years_left": years}}
        )
        ref_id = generate_receipt_ref()
        record_transaction(acc_num, ref_id, f"Asset Lock ({years} Yrs)", -amount)
        receipt = {
            "reference_id": ref_id,
            "status": "ASSET_LOCKED",
            "meta": {
                "transaction_type": "Structural Asset Purchase",
                "locked_value": f"${amount:,.2f}",
                "yield_rate": f"{(user.get('fd_rate', 0.06)*100):.2f}% APR",
                "maturity_horizon": f"{years} Structural Years",
                "issued_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }

    updated_user = accounts_collection.find_one({"account_number": acc_num})
    updated_user["_id"] = str(updated_user["_id"])
    return jsonify({"success": True, "user": updated_user, "receipt": receipt})

@app.route('/api/loan', methods=['POST'])
def draw_loan():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Unauthorized session context."}), 401
    
    acc_num = session['user']
    user = accounts_collection.find_one({"account_number": acc_num})
    if not user:
        return jsonify({"success": False, "error": "Account context missing."}), 404

    data = request.json or {}
    amount = safe_float(data.get('amount', 0))

    if amount <= 0:
        return jsonify({"success": False, "error": "Draw capital requirements must exceed zero."}), 400

    accounts_collection.update_one(
        {"account_number": acc_num}, 
        {"$inc": {"balance": amount, "loan_balance": amount}}
    )

    updated_user = accounts_collection.find_one({"account_number": acc_num})
    updated_user["_id"] = str(updated_user["_id"])

    ref_id = generate_receipt_ref()
    record_transaction(acc_num, ref_id, "Credit Facility Drawdown", amount)

    receipt = {
        "reference_id": ref_id,
        "status": "LOAN_ISSUED",
        "meta": {
            "transaction_type": "Leveraged Credit Facility Drawdown",
            "loaned_amount": f"${amount:,.2f}",
            "financing_rate": f"{(updated_user.get('loan_interest_rate', 0.07)*100):.2f}% Compounding APR",
            "impact_on_liquid": f"+${amount:,.2f} Credit",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    }

    return jsonify({"success": True, "user": updated_user, "receipt": receipt})

@app.route('/api/repay', methods=['POST'])
def repay_loan():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Unauthorized session context."}), 401

    acc_num = session['user']
    user = accounts_collection.find_one({"account_number": acc_num})
    if not user:
        return jsonify({"success": False, "error": "Account context missing."}), 404

    data = request.json or {}
    amount = safe_float(data.get('amount', 0))

    if amount <= 0:
        return jsonify({"success": False, "error": "Repayment value must be greater than zero."}), 400
    if user.get("loan_balance", 0.0) <= 0:
        return jsonify({"success": False, "error": "There is no active liability or debt to repay."}), 400
    if amount > user["balance"]:
        return jsonify({"success": False, "error": "Insufficient liquid funds to complete payback."}), 400

    current_debt = user["loan_balance"]
    # Determine actual payload to deduct (cannot repay more than actual outstanding debt)
    actual_repayment = min(amount, current_debt)

    accounts_collection.update_one(
        {"account_number": acc_num},
        {"$inc": {"balance": -actual_repayment, "loan_balance": -actual_repayment}}
    )

    updated_user = accounts_collection.find_one({"account_number": acc_num})
    updated_user["_id"] = str(updated_user["_id"])

    ref_id = generate_receipt_ref()
    record_transaction(acc_num, ref_id, "Liability Debt Repayment", -actual_repayment)

    receipt = {
        "reference_id": ref_id,
        "status": "REPAYMENT_PROCESSED",
        "meta": {
            "transaction_type": "Liability Repayment Clearance",
            "submitted_repayment": f"${amount:,.2f}",
            "applied_repayment": f"${actual_repayment:,.2f}",
            "remaining_debt": f"${updated_user.get('loan_balance', 0.0):,.2f}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    }

    return jsonify({"success": True, "user": updated_user, "receipt": receipt})

@app.route('/api/timemachine', methods=['POST'])
def time_machine():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Unauthorized session context."}), 401
    
    acc_num = session['user']
    user = accounts_collection.find_one({"account_number": acc_num})
    if not user:
         return jsonify({"success": False, "error": "Ledger config missing."}), 404

    try:
        years_to_skip = int(request.json.get('years', 0))
    except (ValueError, TypeError):
        years_to_skip = 0
        
    if years_to_skip <= 0:
        return jsonify({"success": False, "error": "Chrono-sim increments must be at least 1 Year."}), 400

    balance = user.get("balance", 0.0)
    fd_balance = user.get("fd_balance", 0.0)
    fd_years_left = user.get("fd_years_left", 0)
    fd_rate = user.get("fd_rate", 0.06)
    loan_balance = user.get("loan_balance", 0.0)
    loan_rate = user.get("loan_interest_rate", 0.07)

    initial_liquid = balance
    accrued_fd_yield = 0.0
    accumulated_loan_debt = 0.0
    fd_matured_this_session = False

    for _ in range(years_to_skip):
        # Accrue interest on outstanding loans
        if loan_balance > 0:
            loan_interest = loan_balance * loan_rate
            loan_balance += loan_interest
            accumulated_loan_debt += loan_interest

        # Accrue growth on FD assets
        if fd_balance > 0 and fd_years_left > 0:
            interest = fd_balance * fd_rate
            fd_balance += interest
            fd_years_left -= 1
            accrued_fd_yield += interest
            
            if fd_years_left == 0:
                balance += fd_balance
                fd_matured_this_session = True
                fd_balance = 0.0

    accounts_collection.update_one(
        {"account_number": acc_num},
        {"$set": {
            "balance": balance, 
            "fd_balance": fd_balance, 
            "fd_years_left": fd_years_left,
            "loan_balance": loan_balance
        }}
    )

    updated_user = accounts_collection.find_one({"account_number": acc_num})
    updated_user["_id"] = str(updated_user["_id"])

    ref_id = generate_receipt_ref()
    
    # Save chronological transaction entries inside Database
    if accrued_fd_yield > 0:
        record_transaction(acc_num, ref_id, f"FD Accrued Interest (+{years_to_skip}y)", accrued_fd_yield)
    if accumulated_loan_debt > 0:
        record_transaction(acc_num, ref_id, f"Loan Liability Accumulation (+{years_to_skip}y)", -accumulated_loan_debt)

    receipt = {
        "reference_id": ref_id,
        "status": "CHRONO_SIM_EXEC",
        "meta": {
            "skip_horizon": f"+{years_to_skip} Structural Years",
            "initial_liquid_funds": f"${initial_liquid:,.2f}",
            "updated_liquid_funds": f"${balance:,.2f}",
            "fixed_term_growth": f"+${accrued_fd_yield:,.2f}" if accrued_fd_yield > 0 else "$0.00",
            "liability_accrual": f"+${accumulated_loan_debt:,.2f}" if accumulated_loan_debt > 0 else "$0.00",
            "term_maturity_status": "MATURED & TRANFERRED" if fd_matured_this_session else "STILL ACTIVE" if fd_balance > 0 else "NO_ACTIVE_FD",
            "updated_outstanding_debt": f"${loan_balance:,.2f}"
        }
    }

    return jsonify({"success": True, "user": updated_user, "receipt": receipt})

if __name__ == "__main__":
    # Render sets a PORT environment variable automatically
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
