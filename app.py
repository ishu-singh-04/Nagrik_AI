import os
import random
import string
import json
import base64
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# === FIREBASE IMPORTS ===
import firebase_admin
from firebase_admin import credentials, firestore

# === NEW GOOGLE GENAI SDK ===
from google import genai
from google.genai import types

load_dotenv()
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

UPLOAD_FOLDER = Path("static/uploads")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
# app.py
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB limit
app.config["SECRET_KEY"] = FLASK_SECRET_KEY
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

# Major Indian Cities Metadata for Zoom & Administration Coordinates
CITIES_CONFIG = {
    "Bareilly": {"lat": 28.3670, "lon": 79.4304, "state": "Uttar Pradesh"},
    "Pilibhit": {"lat": 28.6250, "lon": 79.8016, "state": "Uttar Pradesh"},
    "Meerut": {"lat": 28.9845, "lon": 77.7064, "state": "Uttar Pradesh"},
    "Badaun": {"lat": 28.0514, "lon": 79.1247, "state": "Uttar Pradesh"},  # <-- Badaun Add Ho Gaya!
    "Bangalore": {"lat": 12.9716, "lon": 77.5946, "state": "Karnataka"},
    "Lucknow": {"lat": 26.8467, "lon": 80.9462, "state": "Uttar Pradesh"},
    "Noida": {"lat": 28.5355, "lon": 77.3910, "state": "Uttar Pradesh"},
    "Ghaziabad": {"lat": 28.6692, "lon": 77.4538, "state": "Uttar Pradesh"},
    "Kanpur": {"lat": 26.4499, "lon": 80.3319, "state": "Uttar Pradesh"},
    "Agra": {"lat": 27.1767, "lon": 78.0081, "state": "Uttar Pradesh"},
    "Varanasi": {"lat": 25.3176, "lon": 83.0062, "state": "Uttar Pradesh"},
    "Prayagraj": {"lat": 25.4358, "lon": 81.8463, "state": "Uttar Pradesh"},
    "Gorakhpur": {"lat": 26.7606, "lon": 83.3731, "state": "Uttar Pradesh"},
    "Jhansi": {"lat": 25.4484, "lon": 78.5685, "state": "Uttar Pradesh"},
    "Aligarh": {"lat": 27.8974, "lon": 78.0880, "state": "Uttar Pradesh"},
    "Moradabad": {"lat": 28.8351, "lon": 78.7743, "state": "Uttar Pradesh"},
    "Mathura": {"lat": 27.4924, "lon": 77.6737, "state": "Uttar Pradesh"},
    "New Delhi": {"lat": 28.6139, "lon": 77.2090, "state": "Delhi"},
    "Mumbai": {"lat": 19.0760, "lon": 72.8777, "state": "Maharashtra"},
    "Pune": {"lat": 18.5204, "lon": 73.8567, "state": "Maharashtra"},
    "Nagpur": {"lat": 21.1458, "lon": 79.0882, "state": "Maharashtra"},
    "Thane": {"lat": 19.2183, "lon": 72.9781, "state": "Maharashtra"}
}

def setup_firestore_db():
    try:
        officers_ref = db.collection('officers')
        if not list(officers_ref.limit(1).stream()):
            demo_users = [
                {'id': 1, 'email': 'admin@uppcl.gov.in', 'password_hash': generate_password_hash('admin123'), 'department': 'UPPCL', 'category': 'Electricity'},
                {'id': 2, 'email': 'admin@pwd.gov.in', 'password_hash': generate_password_hash('admin123'), 'department': 'PWD', 'category': 'Pothole'},
                {'id': 3, 'email': 'admin@jalnigam.gov.in', 'password_hash': generate_password_hash('admin123'), 'department': 'Jal Nigam', 'category': 'Water'},
                {'id': 4, 'email': 'admin@nagarnigam.gov.in', 'password_hash': generate_password_hash('admin123'), 'department': 'Nagar Nigam', 'category': 'Waste'}
            ]
            for user in demo_users:
                officers_ref.document(user['email']).set(user)
            print("Centralized Demo Officers setup successfully!")
    except Exception as e:
        print("Firestore Setup error:", e)

setup_firestore_db()

def haversine_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, asin
    R = 6371.0; dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * (2 * asin(sqrt(a)))

def generate_ticket_id():
    return f"NAGRIK-{''.join(random.choices(string.digits, k=4))}"

def map_category_and_eta(label: str):
    return {"Pothole": ("Pothole", 72), "Electricity": ("Electricity", 24), "Water": ("Water", 12), "Waste": ("Waste", 48)}.get(label, ("Other", 48))

# ================= AI MODULES =================

def analyze_image_with_gemini(image_bytes: bytes):
    if not GEMINI_API_KEY: 
        return {"category": "Error", "severity": "Low", "description_en": "API Offline", "description_hi": "Error: AI offline"}
        
    import io
    import json
    import re
    import time # Rate limiting ke liye zaroori
    from PIL import Image
    
    # 1. Image Compression (Purana logic intact)
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail([1024, 1024]) 
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        processed_bytes = buffer.getvalue()
    except Exception as e:
        print(f"🚨 Image Compression Error: {e}")
        return {
            "category": "Other", "severity": "Medium", 
            "description_en": "Needs Manual Verification", "description_hi": "मैन्युअल जांच"
        }

    # === SMART PROMPT (With Fake Detection) ===
    prompt = (
        "Analyze this image for civic issues. Return ONLY a valid JSON object with EXACTLY these keys: category, severity, description_en, description_hi.\n"
        "Allowed Categories: Pothole, Electricity, Water, Waste, Fake, Other.\n"
        "Rules:\n"
        "- Map broken roads to 'Pothole', wires/poles to 'Electricity', leaks to 'Water', garbage to 'Waste'.\n"
        "- IF the image is a selfie, portrait, indoor room, meme, or completely unrelated to street issues, MUST set category to 'Fake'.\n"
        "- Return ONLY raw JSON. No markdown formatting."
    )

    # 2. Supported Models Fallback Chain
    models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-flash-latest']
    res = None
    last_error = None

    

   # Token limit explicitly badha do
    config = types.GenerateContentConfig(max_output_tokens=1024)

    for model_name in models_to_try:
        try:
            print(f"🔮 Attempting analysis with model: {model_name}...")
            client = genai.Client(api_key=GEMINI_API_KEY)
            image_part = types.Part.from_bytes(data=processed_bytes, mime_type="image/jpeg")
            
            res = client.models.generate_content(
                model=model_name,
                contents=[image_part, prompt],
                config=config
            )
            if res and res.text:
                print(f"✅ Success with model: {model_name}")
                break
        except Exception as e:
            print(f"⚠️ Model {model_name} overloaded or failed. Error: {e}")
            last_error = e
            time.sleep(2)
            continue

    # 3. Final Smart Parsing & Regex Salvage
    if res and res.text:
        print(f"DEBUG AI RESPONSE: {res.text}") 
        clean_text = res.text.replace('```json', '').replace('```', '').strip()
        
        try:
            # Attempt 1: Strict JSON Parse
            # Check and auto-close string/object if slightly truncated
            if not clean_text.endswith('}'):
                if clean_text.count('"') % 2 != 0:
                    clean_text += '"'
                clean_text += '}'
                
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            else:
                raise ValueError("JSON structure not found")
                
        except Exception as parse_err:
            print(f"🚨 JSON Parsing failed: {parse_err}")
            
            # Attempt 2: Regex Salvage Operation (Hackathon fallback)
            # JSON toot bhi gaya toh kya, hum category extract kar lenge
            cat_match = re.search(r'"category"\s*:\s*"([^"]+)"', clean_text, re.IGNORECASE)
            sev_match = re.search(r'"severity"\s*:\s*"([^"]+)"', clean_text, re.IGNORECASE)
            
            if cat_match:
                salvaged_category = cat_match.group(1)
                salvaged_severity = sev_match.group(1) if sev_match else "Medium"
                print(f"🛠️ Salvaged from broken JSON -> Category: {salvaged_category}")
                return {
                    "category": salvaged_category,
                    "severity": salvaged_severity,
                    "description_en": "Issue detected (Description truncated by AI limit).",
                    "description_hi": "समस्या मिली।"
                }

    # AGAR AI COMPLETELY FAIL HO JAYE
    return {
        "category": "Other", 
        "severity": "Medium", 
        "description_en": "Issue detected (Manual verification needed)", 
        "description_hi": "समस्या मिली (मैन्युअल जांच की आवश्यकता है)"
    }

def verify_repair_with_gemini(before_bytes: bytes, after_bytes: bytes):
    if not GEMINI_API_KEY: 
        return {"is_resolved": True, "score": "90%"}
        
    try:
        import io
        import time
        from PIL import Image
        
        # Secure Before Image Compression
        img_b = Image.open(io.BytesIO(before_bytes))
        img_b.thumbnail([1024, 1024])
        buf_b = io.BytesIO()
        img_b.save(buf_b, format="JPEG")
        
        # Secure After Image Compression
        img_a = Image.open(io.BytesIO(after_bytes))
        img_a.thumbnail([1024, 1024])
        buf_a = io.BytesIO()
        img_a.save(buf_a, format="JPEG")

        client = genai.Client(api_key=GEMINI_API_KEY)
        
        part_before = types.Part.from_bytes(data=buf_b.getvalue(), mime_type="image/jpeg")
        part_after = types.Part.from_bytes(data=buf_a.getvalue(), mime_type="image/jpeg")
        
        prompt = (
            "Compare Image 1 (broken infrastructure) and Image 2 (repaired site). "
            "Respond strictly with JSON containing: 'is_resolved' (bool) and 'score' (percentage string like '95%')"
        )
        
        # === REPLACED VERIFICATION FALLBACK LOOP ===
        models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash']
        res = None
        
        for model_name in models_to_try:
            try:
                print(f"🔮 Attempting verification with model: {model_name}...")
                res = client.models.generate_content(
                    model=model_name,
                    contents=[part_before, part_after, prompt]
                )
                if res and res.text:
                    print(f"✅ Verification Success with: {model_name}")
                    break
            except Exception as e:
                print(f"⚠️ Verify Model {model_name} failed: {e}")
                time.sleep(2)
                continue
        
        clean_text = res.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        return json.loads(match.group(0)) if match else {"is_resolved": True, "score": "85%"}
        
    except Exception as e:
        print(f"🚨 VERIFY REPAIR API ERROR: {e}")
        return {"is_resolved": True, "score": "85%"}

# ================= CITIZEN INFRASTRUCTURE ENDPOINTS =================

@app.route("/")
def index(): 
    return render_template("index.html")

@app.route("/portal")
def portal_page():
    return render_template("report.html")

@app.route("/api/analyze_image", methods=["POST"])
def analyze_image():
    image_file = request.files["image"]
    # FIXED: Using timezone.utc instead of datetime.UTC
    safe_name = f"temp_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{random.randint(1000,9999)}.jpg"
    save_path = UPLOAD_FOLDER / safe_name
    image_file.save(save_path)
    with open(save_path, "rb") as f: 
        ai_data = analyze_image_with_gemini(f.read())
    return jsonify({"success": True, "temp_image_name": safe_name, **ai_data})

# ================= 1. OFFICER LOGIN ROUTE =================
@app.route("/api/officer-login", methods=["POST"])
def api_login():
    data = request.json
    docs = list(db.collection('officers').where('email', '==', data.get('email')).stream())
    
    if docs:
        officer = docs[0].to_dict()
        if check_password_hash(officer['password_hash'], data.get('password')):
            session['officer_id'] = officer.get('id') 
            session['department'] = officer['department']
            session['category'] = officer['category']
            return jsonify({"success": True})
            
    return jsonify({"success": False, "error": "Invalid administrative credentials"}), 401

# ================= 2. CITIZEN SUBMIT ISSUE ROUTE =================
@app.route("/api/submit_issue", methods=["POST"])
def submit_issue():
    data = request.json
    phone = data.get('phone', 'Unknown')
    lat = float(data['latitude'])
    lon = float(data['longitude'])
    category, eta_hours = map_category_and_eta(data['category'])
    
    issues_ref = db.collection('issues')
    
    # Smart Deduplication / Spam Protection Filter
    existing_issues = issues_ref.where('category', '==', category).stream()
    for issue_doc in existing_issues:
        issue = issue_doc.to_dict()
        if issue.get('status') != 'Resolved' and haversine_km(lat, lon, float(issue['latitude']), float(issue['longitude'])) <= 0.05:
            issues_ref.document(issue_doc.id).update({'report_count': firestore.Increment(1)})
            return jsonify({"success": True, "ticket_id": issue_doc.id, "badge": "🏅 Top Reporter (Linked Entry)", "duplicate": True})
            
    old_path = UPLOAD_FOLDER / data['temp_image_name']
    new_name = data['temp_image_name'].replace('temp_', 'final_')
    if old_path.exists(): os.rename(old_path, UPLOAD_FOLDER / new_name)
    
    ticket_id = generate_ticket_id()
    eta_deadline = datetime.now(timezone.utc) + timedelta(hours=eta_hours)
    # === PURE AUTOMATIC GEOLOCATION LOOKUP ENGINE ===
    detected_city = "Bareilly"  # Standard default fallback agar koi city pass na ho
    shortest_distance = float('inf')
    
    for city_name, coords in CITIES_CONFIG.items():
        dist = haversine_km(lat, lon, coords['lat'], coords['lon'])
        if dist < shortest_distance and dist < 100.0:  # radius badha kar 100km kar diya taaki border regions bhi cover ho jayein
            shortest_distance = dist
            detected_city = city_name
    
    # FIXED: Fallback defaults changed hamesha ke liye from Meerut to Bareilly
    issue_data = {
        'ticket_id': ticket_id,
        'latitude': lat, 'longitude': lon,
        'image_url': f"/static/uploads/{new_name}",
        'category': category, 'status': 'Reported', 'report_count': 1,
        'eta_deadline': eta_deadline.strftime("%Y-%m-%d %H:%M"),
        'created_at': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        'description_en': data['description_en'], 'description_hi': data['description_hi'],
        'severity': data['severity'], 'reporter_phone': phone,
        'city': detected_city,  # <--- FIXED: Ab hardcoded nahi, automatic math-detected city save hogi!
        'state': data.get('state', 'Uttar Pradesh'), 
        'pincode': data.get('pincode', '243001')
    }
    
    issues_ref.document(ticket_id).set(issue_data)
    
    user_reports = list(issues_ref.where('reporter_phone', '==', phone).stream())
    reports = len(user_reports)
    badge = "🏅 Civic Starter" if reports < 2 else "🏅 Top Reporter" if reports == 2 else "🏅 Local Hero" if reports < 5 else "🏅 Civic Champion"
    
    return jsonify({"success": True, "ticket_id": ticket_id, "badge": badge, "duplicate": False})

@app.route("/api/track_issue/<ticket_id>", methods=["GET"])
def track_issue(ticket_id):
    doc = db.collection('issues').document(ticket_id.upper()).get()
    if not doc.exists: 
        return jsonify({"success": False, "error": "Ticket not found"}), 404
    return jsonify({"success": True, "issue": doc.to_dict()})

@app.route("/api/public_radar", methods=["GET"])
def public_radar():
    docs = db.collection('issues').stream()
    issues = [doc.to_dict() for doc in docs]
    return jsonify({"success": True, "issues": issues})

# ================= SECURE OFFICER HUB ROUTES =================

@app.route("/officer-login")
def login_page(): 
    return render_template("login.html")

@app.route("/logout")
def logout(): 
    session.clear()
    return redirect(url_for('login_page'))

@app.route("/dashboard")
def dashboard():
    if 'officer_id' not in session: 
        return redirect(url_for('login_page'))
    return render_template("dashboard.html", department=session.get('department'))

@app.route("/api/get_all_issues", methods=["GET"])
def get_all_issues():
    if 'officer_id' not in session: 
        return jsonify({"success": False}), 401
    
    category = session.get('category')
    city = request.args.get('city', 'Bareilly') 
    
    docs = db.collection('issues').where('category', '==', category).where('city', '==', city).stream()
    
    issues = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id 
        issues.append(data)
    
    issues.sort(key=lambda x: (x.get('status') == 'Resolved', x.get('created_at', '')), reverse=True)
    return jsonify({"success": True, "issues": issues})

@app.route("/api/resolve_with_ai", methods=["POST"])
def resolve_with_ai():
    if 'officer_id' not in session: 
        return jsonify({"success": False}), 401
        
    ticket_id = request.form.get("ticket_id")
    status = request.form.get("status")
    
    issue_ref = db.collection('issues').document(ticket_id)
    doc = issue_ref.get()
    
    if not doc.exists:
        return jsonify({"success": False, "error": "Issue not found"}), 404
        
    if status == "In Progress":
        issue_ref.update({"status": "In Progress"})
        return jsonify({"success": True, "message": "Status saved locally"})
        
    if status == "Resolved" and "after_image" in request.files:
        after_file = request.files["after_image"]
        new_name = f"resolved_{ticket_id}_{random.randint(1000,9999)}.jpg"
        after_path = UPLOAD_FOLDER / new_name
        after_file.save(after_path)
        
        before_url = doc.to_dict().get('image_url')
        before_path = str(UPLOAD_FOLDER) + "/" + before_url.split('/')[-1]
        
        with open(before_path, "rb") as f1, open(after_path, "rb") as f2:
            ai_verdict = verify_repair_with_gemini(f1.read(), f2.read())
            
        issue_ref.update({
            "status": "Resolved", 
            "resolved_image_url": f"/static/uploads/{new_name}", 
            "resolution_score": ai_verdict['score']
        })
        return jsonify({"success": True, "score": ai_verdict['score']})
        
    return jsonify({"success": False, "error": "Verification photo execution invalid"}), 400

# ================= NEW: FORWARD/REJECT ISSUE ROUTE =================
@app.route("/api/forward_issue", methods=["POST"])
def forward_issue():
    if 'officer_id' not in session: 
        return jsonify({"success": False}), 401
        
    data = request.json
    ticket_id = data.get('ticket_id')
    reason = data.get('reason', 'No reason provided')
    
    if ticket_id:
        db.collection('issues').document(ticket_id).update({
            "status": "Rejected/Forwarded",
            "notes": reason
        })
        return jsonify({"success": True})
        
    return jsonify({"success": False, "error": "Ticket ID missing"})

@app.route("/static/uploads/<path:filename>")
def uploaded_file(filename): 
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

if __name__ == "__main__": 
    app.run(host="0.0.0.0", port=5000, debug=True)