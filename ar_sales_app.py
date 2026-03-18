"""
Enhanced Sales Accounts Receivable App (Cloud Ready)
Now includes:
- Google Sheets backend (no data loss)
- Login system (username/password)
- All previous AR features
"""

from datetime import datetime
import os
import pandas as pd

# ---------- Streamlit ----------
import streamlit as st

# ---------- Google Sheets Setup ----------
import gspread
from google.oauth2.service_account import Credentials

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Load credentials from Streamlit secrets
@st.cache_resource
def get_gsheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPE
    )
    client = gspread.authorize(creds)
    sheet = client.open("AR_App_Data").sheet1
    return sheet

# ---------- Columns ----------
COLUMNS = [
"Inv Date","Inv No.","Customer","Shipment","POL","Cont.","FOB SGD","Freight","C&F SGD",
"Pymt rcvd","Balance receivable","Terms (days)","Due Date","Collect Date","Overdue days"
]

# ---------- Data ----------
def load_data():
    try:
        sheet = get_gsheet()
        data = sheet.get_all_records()
        df = pd.DataFrame(data)

        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None

        df = df.apply(lambda r: calculate_fields(r), axis=1)
        return df
    except:
        return pd.DataFrame(columns=COLUMNS)


def save_data(df):
    sheet = get_gsheet()
    sheet.clear()
    sheet.append_row(COLUMNS)
    for _, row in df.iterrows():
        sheet.append_row(list(row))

# ---------- Calculations ----------
def calculate_fields(row):
    try:
        if pd.notnull(row.get("Inv Date")) and pd.notnull(row.get("Terms (days)")):
            inv_date_parsed = pd.to_datetime(row["Inv Date"], format="%d-%b-%y", errors="coerce")
            if pd.notnull(inv_date_parsed):
                row["Due Date"] = (inv_date_parsed + pd.Timedelta(days=int(row["Terms (days)"]))).strftime('%d-%b-%y')

        row["C&F SGD"] = float(row.get("FOB SGD",0)) + float(row.get("Freight",0))

        if pd.notnull(row.get("Pymt rcvd")):
            row["Balance receivable"] = row["C&F SGD"] - row["Pymt rcvd"]

        balance = pd.to_numeric(row.get("Balance receivable"), errors="coerce")
        if pd.notnull(balance) and balance == 0:
            row["Due Date"] = ""
            row["Overdue days"] = ""
        else:
            if pd.notnull(row.get("Due Date")):
                due_parsed = pd.to_datetime(row["Due Date"], format="%d-%b-%y", errors="coerce")
                if pd.notnull(due_parsed):
                    days = (pd.Timestamp.today().normalize() - due_parsed).days
                    row["Overdue days"] = max(days, 0)
    except:
        pass
    return row

# ---------- Login System ----------
def login():
    st.sidebar.title("🔐 Login")

    USER = st.secrets["auth"]["username"]
    PASS = st.secrets["auth"]["password"]

    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")

    if username == USER and password == PASS:
        st.session_state["logged_in"] = True
    else:
        st.session_state["logged_in"] = False

# ---------- App ----------
def run_streamlit():

    st.set_page_config(page_title="AR Manager", layout="wide")

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    login()

    if not st.session_state["logged_in"]:
        st.warning("Please login to continue")
        return

    st.title("📊 AR Management System")

    menu = st.sidebar.selectbox("Menu", [
        "Dashboard",
        "Upload Data",
        "Invoice Entry",
        "Edit / Delete",
        "AR Aging"
    ])

    df = load_data()

    df["Balance receivable"] = pd.to_numeric(df["Balance receivable"], errors="coerce")
    open_df = df[df["Balance receivable"].fillna(0) > 0]

    # ---------- Upload Data ----------
    if menu == "Upload Data":
        st.subheader("📤 Upload Excel / CSV")

        uploaded_file = st.file_uploader("Upload file", type=["csv", "xlsx"])

        if uploaded_file:
            try:
                if uploaded_file.name.endswith(".csv"):
                    new_df = pd.read_csv(uploaded_file)
                else:
                    new_df = pd.read_excel(uploaded_file)

                st.write("Preview:")
                st.dataframe(new_df.head())

                # Ensure required columns
                for col in COLUMNS:
                    if col not in new_df.columns:
                        new_df[col] = None

                new_df = new_df[COLUMNS]

                if st.button("Upload to Google Sheets"):
                    new_df = new_df.apply(lambda r: calculate_fields(r), axis=1)
                    save_data(new_df)
                    st.success("Data uploaded successfully ✅")

            except Exception as e:
                st.error(f"Error: {e}")

    # ---------- Dashboard ----------
    if menu == "Dashboard":
        total = open_df["Balance receivable"].sum()
        st.metric("Total Receivable", f"SGD {total:,.2f}")
        st.dataframe(open_df)

    # ---------- Entry ----------
    elif menu == "Invoice Entry":
        with st.form("form"):
            inv_date = st.date_input("Invoice Date")
            inv_no = st.text_input("Invoice No")
            customer = st.text_input("Customer")
            fob = st.number_input("FOB", 0.0)
            freight = st.number_input("Freight", 0.0)
            payment = st.number_input("Payment", 0.0)
            terms = st.number_input("Terms", 0)

            if st.form_submit_button("Save"):
                row = calculate_fields(pd.Series({
                    "Inv Date": pd.to_datetime(inv_date).strftime('%d-%b-%y'),
                    "Inv No.": inv_no,
                    "Customer": customer,
                    "FOB SGD": fob,
                    "Freight": freight,
                    "Pymt rcvd": payment,
                    "Terms (days)": terms
                }))

                df = pd.concat([df, pd.DataFrame([row])])
                save_data(df)
                st.success("Saved to Google Sheets ✅")

    # ---------- Edit/Delete ----------
    elif menu == "Edit / Delete":
        if df.empty:
            st.warning("No data")
            return

        idx = st.selectbox("Select Invoice", df.index)
        row = df.loc[idx]

        new_payment = st.number_input("Payment", value=float(row.get("Pymt rcvd",0)))

        if st.button("Update"):
            df.at[idx, "Pymt rcvd"] = new_payment
            df = df.apply(lambda r: calculate_fields(r), axis=1)
            save_data(df)
            st.success("Updated")

        if st.button("Delete"):
            df = df.drop(idx)
            save_data(df)
            st.warning("Deleted")

    # ---------- Aging ----------
    elif menu == "AR Aging":
        st.dataframe(df)


# ---------- Run ----------
if __name__ == "__main__":
    run_streamlit()
