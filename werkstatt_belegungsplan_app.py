import streamlit as st
import sqlite3
import pandas as pd
import datetime
import urllib.parse
import os

# --- BASE DIRECTORY & DATABASE SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
DB_PATH = os.path.join(BASE_DIR, "werkstatt_data.db")

STATUS_OPTIONS = [
    "1. Intake",
    "2. Inspection",
    "3. in work process",
    "4. Galvanik",
    "5. assembly",
    "6. Acoustic Test",
    "7. Ready"
]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            customer_name TEXT,
            customer_phone TEXT,
            instrument_type TEXT,
            manufacturer TEXT,
            serial_number TEXT,
            repair_type TEXT,
            price_text TEXT,
            status TEXT,
            target_date TEXT,
            notion_url TEXT,
            notes TEXT,
            photo_before TEXT,
            photo_after TEXT,
            archived INTEGER DEFAULT 0,
            completion_date TEXT,
            drive_url TEXT,
            progress_step INTEGER DEFAULT 3,
            invoice_url TEXT,
            created_at TEXT
        )
    """)
    
    cursor.execute("PRAGMA table_info(orders)")
    cols = [c[1] for c in cursor.fetchall()]
    if "drive_url" not in cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN drive_url TEXT DEFAULT ''")
    if "progress_step" not in cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN progress_step INTEGER DEFAULT 3")
    if "invoice_url" not in cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN invoice_url TEXT DEFAULT ''")
    if "created_at" not in cols:
        today_str = str(datetime.date.today())
        cursor.execute(f"ALTER TABLE orders ADD COLUMN created_at TEXT DEFAULT '{today_str}'")
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM orders")
    if cursor.fetchone()[0] == 0:
        today_str = str(datetime.date.today())
        sample_orders = [
            ("REP-2026-001", "Müller, Thomas", "+49 171 123456", "Klarinette", "Buffet Crampon R13", "KL-8821", "Generalüberholung & Mechanik", "850,00 €", "4. Galvanik", "2026-10-05", "https://notion.so/repairlog/kl-8821", "Kunde wünscht Lederpolster im Unterstück.", "https://photos.google.com", "", 0, "", "https://drive.google.com", 4, "https://rechnung.theclarinetlab.de/REP-2026-001", today_str),
            ("REP-2026-002", "Schmidt, Laura", "+49 172 987654", "Querflöte", "Yamaha YFL-312", "QF-3310", "Polsterwechsel & Ausbeulen", "320,00 €", "2. Inspection", "2026-10-03", "", "Grob gereinigt.", "", "", 0, "", "", 2, "", today_str),
            ("REP-2026-007", "Griesi, Annachiara", "+49 170 998877", "Klarinette", "Buffet Crampon RC Prestige", "KL-9901", "Überholung & Versilbern", "920,00 €", "3. in work process", "2026-10-10", "", "The body top joint isn't airtight; I will search for cracks.\nStart disassembling.", "https://photos.google.com", "", 0, "", "https://drive.google.com", 3, "https://rechnung.theclarinetlab.de/REP-2026-007", today_str),
        ]
        cursor.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", sample_orders)
        conn.commit()
    conn.close()

init_db()

def get_orders(archived=0):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM orders WHERE archived = {archived}", conn)
    conn.close()
    return df

def get_order_by_id(order_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, customer_name, customer_phone, instrument_type, manufacturer, 
               serial_number, repair_type, price_text, status, target_date, 
               notion_url, notes, photo_before, photo_after, archived, 
               completion_date, drive_url, progress_step, invoice_url, created_at 
        FROM orders WHERE id = ?
    """, (order_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def save_order(data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO orders 
        (id, customer_name, customer_phone, instrument_type, manufacturer, serial_number, repair_type, price_text, status, target_date, notion_url, notes, photo_before, photo_after, archived, completion_date, drive_url, progress_step, invoice_url, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, data)
    conn.commit()
    conn.close()

def archive_order(order_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cursor.execute("UPDATE orders SET archived = 1, status = '7. Ready', completion_date = ? WHERE id = ?", (today_str, order_id))
    conn.commit()
    conn.close()

def get_query_param(key):
    try:
        if hasattr(st, "query_params"):
            return st.query_params.get(key, None)
        else:
            params = st.experimental_get_query_params()
            res = params.get(key, [None])
            return res[0] if isinstance(res, list) else res
    except Exception:
        return None

# --- PDF LABEL CREATION (100 x 150 mm) ---
from reportlab.lib.pagesizes import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing

def create_label_pdf(order_tuple):
    pdf_path = os.path.join(BASE_DIR, f"label_temp_{order_tuple[0]}.pdf")
    doc = SimpleDocTemplate(pdf_path, pagesize=(100*mm, 150*mm), leftMargin=5*mm, rightMargin=5*mm, topMargin=5*mm, bottomMargin=5*mm)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, leading=18, textColor=colors.HexColor('#0f172a'))
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, leading=13, textColor=colors.HexColor('#475569'))
    bold_style = ParagraphStyle('BoldStyle', parent=styles['Normal'], fontSize=9, leading=12, fontName='Helvetica-Bold')
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=9, leading=11)
    
    inst_type = str(order_tuple[3])
    header_data = [[Paragraph(f"<font color='white'><b>THE CLARINET LAB · {inst_type.upper()}</b></font>", ParagraphStyle('H', parent=styles['Normal'], fontSize=11, alignment=1))]]
    header_table = Table(header_data, colWidths=[90*mm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#0f172a')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 3*mm))
    
    story.append(Paragraph(f"<b>Auftrags-ID:</b> {order_tuple[0]}", subtitle_style))
    story.append(Paragraph(f"<b>Kunde:</b> {order_tuple[1]}", title_style))
    if len(order_tuple) > 2 and order_tuple[2]:
        story.append(Paragraph(f"<b>Tel:</b> {order_tuple[2]}", normal_style))
    story.append(Spacer(1, 3*mm))
    
    created_date = order_tuple[19] if len(order_tuple) > 19 and order_tuple[19] else str(datetime.date.today())
    details_data = [
        [Paragraph("<b>Hersteller:</b>", bold_style), Paragraph(str(order_tuple[4]), normal_style)],
        [Paragraph("<b>Seriennr:</b>", bold_style), Paragraph(str(order_tuple[5]), normal_style)],
        [Paragraph("<b>Erstellt:</b>", bold_style), Paragraph(str(created_date), normal_style)],
        [Paragraph("<b>Fertigstellung:</b>", bold_style), Paragraph(str(order_tuple[9]), normal_style)],
        [Paragraph("<b>Preis / Status:</b>", bold_style), Paragraph(f"{order_tuple[7]} ({order_tuple[8]})", normal_style)],
    ]
    t_details = Table(details_data, colWidths=[28*mm, 62*mm])
    t_details.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_details)
    story.append(Spacer(1, 3*mm))
    
    story.append(Paragraph("<b>Durchzuführende Arbeiten:</b>", bold_style))
    story.append(Paragraph(str(order_tuple[6]), normal_style))
    story.append(Spacer(1, 3*mm))
    
    qr_target = f"https://workshop-vxuta4eusx93wf8ptlhnsn.streamlit.app/?tracking={order_tuple[0]}"
    qr_widget = qr.QrCodeWidget(qr_target)
    bounds = qr_widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    d = Drawing(32*mm, 32*mm, transform=[32*mm/width, 0, 0, 32*mm/height, 0, 0])
    d.add(qr_widget)
    
    qr_table_data = [[d, Paragraph("<b>Scan QR-Code:</b><br/>Öffnet Live-Kundenansicht.", normal_style)]]
    qr_table = Table(qr_table_data, colWidths=[36*mm, 54*mm])
    qr_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(qr_table)
    
    doc.build(story)
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    try:
        os.remove(pdf_path)
    except Exception:
        pass
    return pdf_bytes

# --- STREAMLIT PAGE CONFIG ---
st.set_page_config(page_title="THE CLARINET LAB", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS FOR STYLING ---
st.markdown("""
<style>
    .header-container {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        padding: 24px 32px;
        border-radius: 12px;
        color: #ffffff;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        border-bottom: 4px solid #d97706;
    }
    .header-title {
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-size: 28px;
        font-weight: 800;
        letter-spacing: 2px;
        color: #ffffff;
        margin: 0;
        text-transform: uppercase;
    }
    .header-subtitle {
        font-size: 14px;
        color: #94a3b8;
        margin-top: 4px;
        letter-spacing: 1px;
    }
    
    .invoice-card {
        background-color: #f0fdf4;
        border: 2px solid #16a34a;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 10px rgba(22, 163, 74, 0.12);
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
    }
    .invoice-amount {
        font-size: 32px;
        font-weight: 800;
        color: #15803d;
        margin: 8px 0;
    }
    
    .card-klarinette {
        background-color: #f0f9ff;
        border-left: 6px solid #0284c7;
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    .card-querfloete {
        background-color: #fff7ed;
        border-left: 6px solid #ea580c;
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    .card-sonstiges {
        background-color: #f8fafc;
        border-left: 6px solid #475569;
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    
    .badge-status {
        background-color: #fef3c7;
        color: #b45309;
        font-weight: bold;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.85em;
    }
    
    .stepper-circle {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background-color: #cbd5e1;
        color: #475569;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto 8px auto;
        font-weight: bold;
        font-size: 15px;
        border: 3px solid #ffffff;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    .stepper-circle.active {
        background-color: #d97706;
        color: #ffffff;
        border: 3px solid #fef3c7;
        box-shadow: 0 0 0 4px rgba(217, 119, 6, 0.3);
    }
    .stepper-circle.completed {
        background-color: #0f172a;
        color: #ffffff;
    }
    .stepper-label {
        font-size: 12px;
        font-weight: 700;
        color: #1e293b;
    }
    .stepper-sublabel {
        font-size: 10px;
        color: #64748b;
        margin-top: 2px;
    }
</style>
""", unsafe_allow_html=True)

# --- CHECK QUERY PARAMS FOR CUSTOMER LIVE TRACKING MODE ---
tracking_id = get_query_param("tracking")

if tracking_id:
    # --- CUSTOMER PORTAL VIEW (ENGLISH) ---
    order_data = get_order_by_id(tracking_id)
    
    st.markdown("""
    <div class="header-container">
        <div class="header-title">THE CLARINET LAB</div>
        <div class="header-subtitle">MASTER CRAFTSMAN WORKSHOP · LIVE REPAIR PORTAL</div>
    </div>
    """, unsafe_allow_html=True)
    
    if not order_data:
        st.error(f"Repair Order #{tracking_id} not found. Please verify your link or contact the workshop.")
    else:
        o_id, o_cust, o_phone, o_inst, o_manuf, o_sn, o_repair, o_price, o_status, o_date, o_notion, o_notes, o_pbefore, o_pafter, o_arch, o_cdate, o_drive, o_step, o_invoice, o_created = order_data[:20]
        
        # Resolve current step (1 to 7) based on status or progress_step
        current_step = 3
        if o_status in STATUS_OPTIONS:
            current_step = STATUS_OPTIONS.index(o_status) + 1
        elif o_step:
            current_step = int(o_step)
            
        st.markdown(f"### Live Repair Journey for {o_cust}")
        
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.info(f"**Instrument:** {o_manuf} ({o_inst})\n\n**Serial No:** {o_sn}")
        with col_c2:
            st.warning(f"**Current Status:** {o_status}\n\n**Order ID:** {o_id}")
        with col_c3:
            st.success(f"**Estimated Completion:** {o_date}\n\n**Repair Scope:** {o_repair}")
            
        # --- INVOICE & PAYMENT SECTION FOR CUSTOMER ---
        if o_invoice or o_price:
            st.markdown("---")
            st.markdown("#### 📄 Invoice & Payment Information")
            
            inv_col1, inv_col2 = st.columns([1, 1])
            with inv_col1:
                st.markdown(f"""
                <div class="invoice-card">
                    <div style="font-size:14px; font-weight:bold; color:#166534; text-transform:uppercase; letter-spacing:1px;">Rechnungsbetrag / Total Invoice Amount</div>
                    <div class="invoice-amount">{o_price if o_price else 'Available on Invoice'}</div>
                    <div style="font-size:13px; color:#15803d;">Craftsmanship & Service for Order #{o_id}</div>
                </div>
                """, unsafe_allow_html=True)
                
            with inv_col2:
                st.write("")
                st.write("")
                if o_invoice:
                    st.markdown(f"""
                    <a href="{o_invoice}" target="_blank" style="text-decoration:none;">
                        <div style="background-color:#16a34a; color:white; font-weight:bold; font-size:18px; padding:18px 24px; border-radius:10px; text-align:center; box-shadow:0 4px 8px rgba(0,0,0,0.15);">
                            📄 View & Download Official Invoice (PDF)
                        </div>
                    </a>
                    """, unsafe_allow_html=True)
                    st.caption("Click above to open or download your official PDF invoice.")
                else:
                    st.info("The digital PDF invoice link will be published here upon completion.")

        # --- PROGRESS MILESTONES (7 STEPS) ---
        st.markdown("---")
        st.markdown("#### ⚙️ Service Milestones & Progress")
        
        steps = [
            ("1. Intake", "Disassembly & Logging"),
            ("2. Inspection", "Mechanics & Tone Holes"),
            ("3. in work process", "Craftsmanship & Repair"),
            ("4. Galvanik", "Electroplating & Silvering"),
            ("5. assembly", "Precision Padding & Fitting"),
            ("6. Acoustic Test", "Playability & Intonation"),
            ("7. Ready", "Final Quality Control")
        ]
        
        step_cols = st.columns(7)
        for idx, (title, subtitle) in enumerate(steps, start=1):
            with step_cols[idx-1]:
                if idx < current_step:
                    circle_html = '<div class="stepper-circle completed">✓</div>'
                elif idx == current_step:
                    circle_html = f'<div class="stepper-circle active">{idx}</div>'
                else:
                    circle_html = f'<div class="stepper-circle">{idx}</div>'
                    
                st.markdown(f"""
                <div style="text-align: center; padding: 4px;">
                    {circle_html}
                    <div class="stepper-label">{title}</div>
                    <div class="stepper-sublabel">{subtitle}</div>
                </div>
                """, unsafe_allow_html=True)
                
        st.markdown("---")
        
        col_w1, col_w2 = st.columns([1, 1])
        with col_w1:
            st.markdown("#### 💬 Direct Communication")
            msg_text = f"Hello Master Craftsman, I have a question regarding my instrument repair (Order #{o_id})..."
            wa_url = f"https://wa.me/49171123456?text={urllib.parse.quote(msg_text)}"
            st.markdown(f"""
            <a href="{wa_url}" target="_blank" style="text-decoration:none;">
                <div style="background-color:#25D366; color:white; font-weight:bold; padding:14px 20px; border-radius:8px; text-align:center; margin-bottom:12px; box-shadow:0 2px 4px rgba(0,0,0,0.1);">
                    💬 Chat with Master Technician on WhatsApp
                </div>
            </a>
            """, unsafe_allow_html=True)
            st.caption("Feel free to send us a direct message anytime regarding your instrument.")
            
        with col_w2:
            st.markdown("#### 📝 Technician Log Notes")
            if o_notes and o_notes.strip() and o_notes.strip() != o_repair.strip():
                lines = [line.strip() for line in o_notes.split("\n") if line.strip()]
                for l in lines:
                    st.markdown(f"• {l}")
            elif o_notes and o_notes.strip():
                st.write("Work proceeding as outlined in repair scope.")
            else:
                st.write("Instrument undergoing precision craftsmanship.")
                
        # --- CUSTOMER GOOGLE PHOTOS ALBUM LINK ---
        gphotos_url = o_pbefore if o_pbefore and o_pbefore.startswith("http") else None
        if gphotos_url:
            st.markdown("---")
            st.markdown("#### 📸 Repair Photo Gallery (Google Photos)")
            st.markdown(f"""
            <a href="{gphotos_url}" target="_blank" style="text-decoration:none;">
                <div style="background-color:#ea4335; color:white; font-weight:bold; font-size:16px; padding:16px 20px; border-radius:10px; text-align:center; box-shadow:0 4px 8px rgba(0,0,0,0.12);">
                    📸 View Repair Photos & Album on Google Photos
                </div>
            </a>
            """, unsafe_allow_html=True)
            st.caption("Click above to view all high-resolution repair photos and updates in your Google Photos album.")



else:
    # --- INTERNAL WORKSHOP MANAGEMENT APP ---
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "📋 Belegungsplan"
        
    st.markdown("""
    <div class="header-container">
        <div class="header-title">THE CLARINET LAB</div>
        <div class="header-subtitle">WERKSTATT BELEGUNGSPLAN & INSTRUMENTEN-TRACKING</div>
    </div>
    """, unsafe_allow_html=True)
    
    page_options = ["📋 Belegungsplan", "🔍 Detailansicht & Bearbeitung", "📁 Archiv"]
    
    current_idx = page_options.index(st.session_state["current_page"]) if st.session_state["current_page"] in page_options else 0
    selected_page = st.radio(
        "Navigation", 
        page_options, 
        index=current_idx,
        horizontal=True,
        label_visibility="collapsed"
    )
    
    if selected_page != st.session_state["current_page"]:
        st.session_state["current_page"] = selected_page
        st.rerun()

    page = st.session_state["current_page"]

    # --- PAGE 1: BELEGUNGSPLAN ---
    if page == "📋 Belegungsplan":
        df_active = get_orders(archived=0)
        
        col_f1, col_f2, col_btn = st.columns([2, 2, 2])
        with col_f1:
            status_filter = st.selectbox("Status Filter", ["Alle Status"] + STATUS_OPTIONS)
        with col_f2:
            inst_filter = st.selectbox("Instrumenten Filter", ["Alle Instrumente", "Klarinette", "Querflöte", "Sonstiges"])
        with col_btn:
            st.write("")
            st.write("")
            if st.button("➕ Neuer Auftrag anlegen", type="primary"):
                st.session_state["selected_order_id"] = "NEW"
                st.session_state["current_page"] = "🔍 Detailansicht & Bearbeitung"
                st.rerun()

        df_filtered = df_active.copy()
        if status_filter != "Alle Status":
            df_filtered = df_filtered[df_filtered["status"] == status_filter]
        if inst_filter != "Alle Instrumente":
            if inst_filter == "Sonstiges":
                df_filtered = df_filtered[~df_filtered["instrument_type"].isin(["Klarinette", "Querflöte"])]
            else:
                df_filtered = df_filtered[df_filtered["instrument_type"] == inst_filter]

        st.markdown("---")
        st.subheader(f"Aktive Belegungs-Kacheln ({len(df_filtered)} Aufträge)")

        if len(df_filtered) == 0:
            st.info("Keine aktiven Aufträge für die gewählten Filter gefunden.")
        else:
            cols = st.columns(3)
            for idx, row in df_filtered.reset_index(drop=True).iterrows():
                col = cols[idx % 3]
                with col:
                    inst_type = str(row["instrument_type"])
                    card_class = "card-klarinette" if "Klarinette" in inst_type else ("card-querfloete" if "Querflöte" in inst_type else "card-sonstiges")
                    
                    created_date_str = str(row["created_at"]) if "created_at" in row and row["created_at"] else str(datetime.date.today())
                    target_date_str = str(row["target_date"])
                    
                    st.markdown(f"""
                    <div class="{card_class}">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:bold; font-size:1.1em; color:#1e293b;">{inst_type.upper()}</span>
                            <span style="font-size:0.85em; color:#64748b;">SN: {row['serial_number']}</span>
                        </div>
                        <h3 style="margin: 8px 0 4px 0; color:#0f172a;">{row['customer_name']}</h3>
                        <p style="margin: 0; color:#475569; font-size:0.95em;"><b>Auftrag:</b> {row['repair_type']}</p>
                        <div style="margin-top: 10px; display:flex; justify-content:space-between; align-items:center;">
                            <span class="badge-status">{row['status']}</span>
                            <span style="font-size:0.85em; color:#0f172a; font-weight:bold;">{row['price_text']}</span>
                        </div>
                        <div style="margin-top: 8px; font-size:0.8em; color:#64748b; display:flex; justify-content:space-between;">
                            <span>🗓️ Erstellt: {created_date_str}</span>
                            <span>📅 Fertig: {target_date_str}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    btn_c1, btn_c2 = st.columns(2)
                    with btn_c1:
                        if st.button(f"🔍 Details #{row['id']}", key=f"btn_det_{row['id']}"):
                            st.session_state["selected_order_id"] = row["id"]
                            st.session_state["current_page"] = "🔍 Detailansicht & Bearbeitung"
                            st.rerun()
                    with btn_c2:
                        order_row_tuple = (
                            row['id'], row['customer_name'], row['customer_phone'], row['instrument_type'], 
                            row['manufacturer'], row['serial_number'], row['repair_type'], row['price_text'], 
                            row['status'], row['target_date'], row['notion_url'], row['notes'], 
                            row['photo_before'], row['photo_after'], row['archived'], row['completion_date'], 
                            row.get('drive_url', ''), row.get('progress_step', 3), row.get('invoice_url', ''), 
                            created_date_str
                        )
                        pdf_data = create_label_pdf(order_row_tuple)
                        st.download_button(
                            label="🖨️ Label (PDF)",
                            data=pdf_data,
                            file_name=f"Etikett_{row['id']}.pdf",
                            mime="application/pdf",
                            key=f"dl_lbl_{row['id']}"
                        )

    # --- PAGE 2: DETAILANSICHT & BEARBEITUNG ---
    elif page == "🔍 Detailansicht & Bearbeitung":
        df_active = get_orders(archived=0)
        active_ids = df_active["id"].tolist() if len(df_active) > 0 else []
        
        selected_id = st.session_state.get("selected_order_id", None)
        
        col_sel1, col_sel2 = st.columns([3, 1])
        with col_sel1:
            if active_ids:
                default_pos = active_ids.index(selected_id) if selected_id in active_ids else 0
                chosen_id = st.selectbox("Auftrag zur Bearbeitung auswählen", active_ids, index=default_pos)
                if chosen_id != selected_id and selected_id != "NEW":
                    st.session_state["selected_order_id"] = chosen_id
                    selected_id = chosen_id
        with col_sel2:
            st.write("")
            st.write("")
            if st.button("➕ Neuer Auftrag"):
                st.session_state["selected_order_id"] = "NEW"
                st.rerun()

        if not selected_id and active_ids:
            selected_id = active_ids[0]
            st.session_state["selected_order_id"] = selected_id

        today_str = str(datetime.date.today())
        if not selected_id or selected_id == "NEW":
            st.subheader("➕ Neuen Reparaturauftrag anlegen")
            current_order = ("", "", "", "Klarinette", "", "", "", "", "1. Intake", today_str, "", "", "", "", 0, "", "", 1, "", today_str)
            new_id = f"REP-{datetime.date.today().year}-{len(get_orders(archived=0))+len(get_orders(archived=1))+1:03d}"
            is_new = True
        else:
            current_order = get_order_by_id(selected_id)
            if not current_order:
                st.warning("Auftrag nicht gefunden.")
                st.stop()
            new_id = current_order[0]
            st.subheader(f"⚙️ Auftragsdetails: {current_order[1]} (ID: {new_id})")
            is_new = False

        c_left, c_right = st.columns([1, 1])
        
        with c_left:
            st.markdown("### 📋 Stammdaten & Reparatur")
            cust_name = st.text_input("Kundenname", value=current_order[1])
            cust_phone = st.text_input("Telefon / Kontakt", value=current_order[2])
            
            inst_options = ["Klarinette", "Querflöte", "Sonstiges (Freitext)"]
            default_idx = 0 if "Klarinette" in current_order[3] else (1 if "Querflöte" in current_order[3] else 2)
            inst_choice = st.selectbox("Instrumententyp", inst_options, index=default_idx)
            
            if inst_choice == "Sonstiges (Freitext)":
                inst_custom = st.text_input("Spezifisches Instrument eingeben", value=current_order[3] if default_idx == 2 else "Saxophon")
                final_inst = f"Sonstiges ({inst_custom})"
            else:
                final_inst = inst_choice
                
            manufacturer = st.text_input("Hersteller & Modell", value=current_order[4])
            serial_no = st.text_input("Seriennummer", value=current_order[5])
            repair_desc = st.text_area("Reparaturart / Durchzuführende Arbeiten", value=current_order[6])
            
            price_val = st.text_input("Rechnungsbetrag / Preis (Freitext)", value=current_order[7], help="z. B. '920,00 €' - wird dem Kunden in groß angezeigt")
            invoice_url_val = st.text_input("Rechnungs-URL / PDF Link für Kunden", value=current_order[18] if len(current_order)>18 else "", help="Link zur Kundenseite der Rechnung")
            
            status_idx = STATUS_OPTIONS.index(current_order[8]) if current_order[8] in STATUS_OPTIONS else 0
            status_val = st.selectbox("Status (Phasen 1 bis 7)", STATUS_OPTIONS, index=status_idx)
            step_val = STATUS_OPTIONS.index(status_val) + 1
            
            target_date = st.text_input("Geplantes Fertigstellungsdatum", value=current_order[9])
            created_at_val = current_order[19] if len(current_order) > 19 and current_order[19] else today_str
            st.text_input("Erstellungsdatum (Automatisch)", value=created_at_val, disabled=True)

        with c_right:
            st.markdown("### 🔗 Links & Interne Verwaltung")
            
            local_ip_link = f"https://workshop-vxuta4eusx93wf8ptlhnsn.streamlit.app/?tracking={new_id}"
            localhost_link = f"http://localhost:8501/?tracking={new_id}"
            
            st.text_input("Kunden-Live-Link (Werkstatt-WLAN IP)", value=local_ip_link, help="Diesen Link per WhatsApp/E-Mail an den Kunden senden")
            st.text_input("Kunden-Live-Link (Localhost Test)", value=localhost_link)
            
            phone_clean = "".join([c for c in cust_phone if c.isdigit() or c=='+'])
            wa_text = f"Hello {cust_name}, your {final_inst} ({manufacturer}, Order #{new_id}) is currently in our workshop at The Clarinet Lab! Track your repair progress live here: {local_ip_link}"
            wa_share_url = f"https://wa.me/{phone_clean}?text={urllib.parse.quote(wa_text)}"
            
            st.markdown(f"""
            <a href="{wa_share_url}" target="_blank" style="text-decoration:none;">
                <div style="background-color:#25D366; color:white; font-weight:bold; padding:10px 16px; border-radius:6px; text-align:center; margin-bottom:12px;">
                    💬 Send English Live-Tracking Link via WhatsApp
                </div>
            </a>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("### 📸 Google Photos Album (Kundenseite & Werkstatt)")
            gphotos_url_val = st.text_input("Google Photos Album URL (Link für Kunden-Fotos)", value=current_order[12] if len(current_order)>12 else "", help="Füge hier den Freigabe-Link zu deinem Google Photos Album für diesen Kunden ein.")
            if gphotos_url_val and gphotos_url_val.startswith("http"):
                st.markdown(f"""
                <a href="{gphotos_url_val}" target="_blank" style="text-decoration:none;">
                    <div style="background-color:#ea4335; color:white; font-weight:bold; padding:12px 18px; border-radius:8px; text-align:center; margin-bottom:12px;">
                        📸 Google Photos Album im Browser öffnen
                    </div>
                </a>
                """, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### 📁 Interne Dokumente & Google Drive (Werkstatt)")
            drive_url_val = st.text_input("Google Drive Ordner URL (Interne Reparaturabläufe & Listen)", value=current_order[16] if len(current_order)>16 else "")
            if drive_url_val:
                st.markdown(f"""
                <a href="{drive_url_val}" target="_blank" style="text-decoration:none;">
                    <div style="background-color:#0284c7; color:white; font-weight:bold; padding:10px 16px; border-radius:6px; text-align:center; margin-bottom:12px;">
                        📁 Internen Google Drive Ordner im Browser öffnen
                    </div>
                </a>
                """, unsafe_allow_html=True)
            
            notion_url = st.text_input("Link zu Notion RepairLog", value=current_order[10])
            
            st.markdown("---")
            st.markdown("### 📝 Techniker Notizen")
            notes_text = st.text_area("Freitext Notizen (Technician Log - Zeile für Zeile)", value=current_order[11], height=100)

            st.markdown("---")
            st.markdown("### 🖨️ Label Drucken (100 x 150 mm)")
            pdf_label_bytes = create_label_pdf(current_order)
            st.download_button(
                label="🖨️ PDF-Etikett herunterladen & drucken (100x150 mm)",
                data=pdf_label_bytes,
                file_name=f"Etikett_{new_id}.pdf",
                mime="application/pdf",
                key=f"dl_lbl_detail_{new_id}"
            )

            st.markdown("---")
            st.markdown("### 💾 Aktionen")
            col_act1, col_act2 = st.columns(2)
            with col_act1:
                if st.button("💾 Speichern", type="primary", use_container_width=True):
                    order_tuple = (new_id, cust_name, cust_phone, final_inst, manufacturer, serial_no, repair_desc, price_val, status_val, target_date, notion_url, notes_text, gphotos_url_val, "", 0, "", drive_url_val, step_val, invoice_url_val, created_at_val)
                    save_order(order_tuple)
                    st.success("Erfolgreich gespeichert!")
                    st.session_state["selected_order_id"] = new_id
                    st.rerun()

            with col_act2:
                if not is_new:
                    if st.button("✅ Fertigstellen & Archivieren", use_container_width=True):
                        archive_order(new_id)
                        st.success(f"Auftrag #{new_id} wurde archiviert!")
                        st.session_state["selected_order_id"] = None
                        st.session_state["current_page"] = "📋 Belegungsplan"
                        st.rerun()

    # --- PAGE 3: ARCHIV ---
    elif page == "📁 Archiv":
        st.subheader("📁 Archivierte Reparaturaufträge")
        df_archived = get_orders(archived=1)
        
        if len(df_archived) == 0:
            st.info("Noch keine archivierten Aufträge vorhanden.")
        else:
            show_cols = ["id", "customer_name", "instrument_type", "manufacturer", "serial_number", "repair_type", "price_text", "created_at", "completion_date"]
            available_show_cols = [c for c in show_cols if c in df_archived.columns]
            st.dataframe(df_archived[available_show_cols], use_container_width=True)
