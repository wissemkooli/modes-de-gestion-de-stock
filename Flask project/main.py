import matplotlib
matplotlib.use('Agg')  # ⭐ AJOUTEZ CETTE LIGNE AU DÉBUT
from flask import Flask, redirect, url_for, render_template, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import base64
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return render_template("templatemo_592_glossy_touch/index.html")

# ---------------------------
# ABC Analysis Backend Functions
# ---------------------------
def abc_analysis(df):
    """Classify inventory items into A, B, C categories."""
    df["Annual_Usage"] = df["Quantity"] * df["Unit_Cost"]
    df = df.sort_values("Annual_Usage", ascending=False)
    df["Cumulative_Percentage"] = (df["Annual_Usage"].cumsum() / df["Annual_Usage"].sum()) * 100
    
    # Classify A (Top 80%), B (Next 15%), C (Remaining 5%)
    df["ABC_Class"] = np.where(
        df["Cumulative_Percentage"] <= 80, "A",
        np.where(df["Cumulative_Percentage"] <= 95, "B", "C")
    )
    
    return df

def calculate_reorder_point(df, safety_stock=10):
    """Calculate reorder points for each item."""
    df["Reorder_Point"] = (df["Quantity"] / 30) * df["Lead_Time_Days"] + safety_stock
    return df

def calculate_eoq(df, ordering_cost=50, holding_rate=0.2):
    """Calculate EOQ for each item."""
    df["Holding_Cost"] = df["Unit_Cost"] * holding_rate
    df["EOQ"] = np.sqrt((2 * df["Quantity"] * ordering_cost) / df["Holding_Cost"])
    return df

def create_abc_chart(df):
    """Create ABC classification chart and return as base64"""
    plt.figure(figsize=(10, 6))
    
    # Create the chart
    abc_counts = df["ABC_Class"].value_counts()
    colors = ['#2ed573', '#ffa502','#ff4757']
    abc_counts.plot(kind='bar', color=colors)
    
    plt.xlabel('ABC Class')
    plt.ylabel('Number of Items')
    plt.xticks(rotation=0)
    plt.grid(axis='y', alpha=0.3)
    
    # Convert to base64 for HTML
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight', dpi=100)
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()
    plt.close()
    
    return f"data:image/png;base64,{plot_url}"

def create_cumulative_chart(df):
    """Create cumulative percentage chart and return as base64"""
    plt.figure(figsize=(10, 6))  # Même taille que le bar chart
    
    # Trier les données par usage annuel (déjà fait dans abc_analysis)
    df_sorted = df.sort_values("Annual_Usage", ascending=False)
    
    # Créer la courbe cumulative
    items_count = range(1, len(df_sorted) + 1)
    cumulative_percentage = df_sorted["Cumulative_Percentage"].values
    
    # Tracer la courbe
    plt.plot(items_count, cumulative_percentage, linewidth=3, color='#667eea', marker='o', markersize=4)
    plt.fill_between(items_count, cumulative_percentage, alpha=0.3, color='#667eea')
    
    # Ajouter les lignes de séparation A/B/C
    plt.axhline(y=80, color='#ff4757', linestyle='--', alpha=0.7, label='A/B Boundary (80%)')
    plt.axhline(y=95, color='#ffa502', linestyle='--', alpha=0.7, label='B/C Boundary (95%)')
    
    # Style du graphique
    plt.xlabel('Number of Items (Sorted by Value)')
    plt.ylabel('Cumulative Percentage of Total Value (%)')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.xlim(1, len(df_sorted))
    plt.ylim(0, 100)
    
    # Convertir en base64
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight', dpi=100)
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()
    plt.close()
    
    return f"data:image/png;base64,{plot_url}"

# ---------------------------
# API Endpoint for ABC Analysis
# ---------------------------
@app.route('/analyze-inventory', methods=['POST'])
def analyze_inventory():
    try:
        # Get data from frontend
        inventory_data = request.json
        
        # Convert to DataFrame
        df = pd.DataFrame(inventory_data)
        
        # Perform analysis
        df = abc_analysis(df)
        df = calculate_reorder_point(df)
        df = calculate_eoq(df)
        
        # Create visualization
        bar_chart_url = create_abc_chart(df)
        cumulative_chart_url = create_cumulative_chart(df)
        
        # Convert results to dictionary for JSON response
        results = df.to_dict('records')
        
        return jsonify({
            'success': True,
            'results': results,
            'bar_chart': bar_chart_url,           # Changé de 'chart'
            'cumulative_chart': cumulative_chart_url,  # Nouveau
            'summary': {
                'total_items': len(df),
                'a_items': len(df[df['ABC_Class'] == 'A']),
                'b_items': len(df[df['ABC_Class'] == 'B']),
                'c_items': len(df[df['ABC_Class'] == 'C']),
                'total_value': df['Annual_Usage'].sum()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Configuration email (fake account)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = "fake.stock.alert@gmail.com"  # Votre faux Gmail
SENDER_PASSWORD = "yuuo bnlt jobt ovoy"  # Reste dans le code

def send_stock_alert(item_name, current_qty, reorder_point, recipient_email):
    """Send low-stock alert via Gmail."""
    try:
        msg = EmailMessage()
        msg["Subject"] = f"⚠️ Low Stock Alert: {item_name}"
        msg["From"] = SENDER_EMAIL
        msg["To"] = recipient_email
        
        msg.set_content(f"""
        📦 INVENTORY ALERT - Action Required!
        
        Item: {item_name}
        Current Quantity: {current_qty}
        Reorder Point: {reorder_point}
        Status: ❌ BELOW REORDER POINT
        
        Please reorder immediately to avoid stockout.
        """)

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Alert sent for {item_name} to {recipient_email}")
        return True
        
    except Exception as e:
        print(f"❌ Email failed: {str(e)}")
        return False

# Route pour envoyer les alertes
@app.route('/api/send-stock-alerts', methods=['POST'])
def send_stock_alerts():
    data = request.get_json()
    critical_items = data.get('critical_items', [])
    
    results = []
    for item in critical_items:
        success = send_stock_alert(
            item_name=item['Item_Name'],
            current_qty=item['Quantity'],
            reorder_point=item['Reorder_Point'],
            recipient_email="manager@company.com"  # Email du destinataire
        )
        results.append({
            'item': item['Item_Name'],
            'alert_sent': success
        })
    
    return jsonify({
        'success': True,
        'message': f'{len([r for r in results if r["alert_sent"]])} alerts sent',
        'results': results
    })

if __name__ == '__main__':
    app.run(debug=True)