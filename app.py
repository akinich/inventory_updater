import streamlit as st
import requests
import pandas as pd
import math
import openpyxl  # required for reading .xlsx via pandas

st.set_page_config(page_title="WooCommerce Product Lookup & Update", layout="wide")
st.title("WooCommerce Product Lookup & Inline Update")

# WooCommerce API credentials
WC_API_URL = st.secrets.get("WC_API_URL", "https://sustenance.co.in/wp-json/wc/v3")
WC_CONSUMER_KEY = st.secrets.get("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = st.secrets.get("WC_CONSUMER_SECRET")

if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
    st.error("WooCommerce credentials are missing. Please set WC_CONSUMER_KEY and WC_CONSUMER_SECRET in secrets.")
    st.stop()

@st.cache_data(show_spinner=False)
def load_item_database():
    try:
        df = pd.read_excel("item_database.xlsx", engine="openpyxl")
        if "ID" not in df.columns:
            st.warning("item_database.xlsx does not contain an 'ID' column.")
            return None
        df = df[df["ID"].notna()].copy()
        df["ID"] = df["ID"].astype(int)
        return df
    except FileNotFoundError:
        st.warning("item_database.xlsx not found in the app directory.")
        return None
    except ImportError as e:
        st.error(f"Excel reading requires openpyxl. Please install it. Error: {e}")
        return None
    except Exception as e:
        st.error(f"Error reading item_database.xlsx: {e}")
        return None

def safe_get(url, params=None):
    try:
        return requests.get(url, params=params, auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET), timeout=30)
    except Exception as e:
        class R:
            status_code = 0
            text = str(e)
            def json(self): return {}
        return R()

def fetch_products_for_ids(source_ids):
    df_rows = []
    id_to_manage_stock = {}
    missing_ids = []

    source_id_set = set(int(i) for i in source_ids if pd.notna(i))

    parents_to_expand = set()
    fetched_products_by_id = {}

    for pid in sorted(source_id_set):
        r = safe_get(f"{WC_API_URL}/products/{pid}")
        if r.status_code in (404, 403):
            missing_ids.append(pid)
            continue
        if r.status_code != 200:
            missing_ids.append(pid)
            continue

        p = r.json()
        fetched_products_by_id[p.get("id")] = p
        id_to_manage_stock[p.get("id")] = bool(p.get("manage_stock"))

        df_rows.append({
            "ID": p.get("id"),
            "Parent ID": None if p.get("type") != "variation" else p.get("parent_id"),
            "Product Name": p.get("name"),
            "Current Stock": p.get("stock_quantity") or 0,
            "Sale Price": p.get("sale_price") or "",
            "Regular Price": p.get("regular_price") or "",
            "Type": p.get("type") or "simple",
            "New Sale Price": "",
            "New Stock Quantity": "",
        })

        if p.get("type") == "variable":
            parents_to_expand.add(p.get("id"))

    for parent_id in sorted(parents_to_expand):
        var_page = 1
        while True:
            vr = safe_get(
                f"{WC_API_URL}/products/{parent_id}/variations",
                params={"per_page": 100, "page": var_page}
            )
            if vr.status_code != 200:
                break
            variations = vr.json()
            if not variations:
                break
            for v in variations:
                id_to_manage_stock[v.get("id")] = bool(v.get("manage_stock"))
                df_rows.append({
                    "ID": v.get("id"),
                    "Parent ID": parent_id,
                    "Product Name": v.get("name") or (fetched_products_by_id.get(parent_id) or {}).get("name"),
                    "Current Stock": v.get("stock_quantity") or 0,
                    "Sale Price": v.get("sale_price") or "",
                    "Regular Price": v.get("regular_price") or "",
                    "Type": "variation",
                    "New Sale Price": "",
                    "New Stock Quantity": "",
                })
            var_page += 1

    return df_rows, id_to_manage_stock, sorted(missing_ids)

def is_blank(value):
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False

def coerce_int(value):
    if is_blank(value):
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None

def coerce_price(value):
    if is_blank(value):
        return ""
    s = str(value).strip()
    return "" if s.lower() == "nan" else s

# Initialize session state
if "products_df" not in st.session_state:
    st.session_state["products_df"] = None
if "manage_stock_map" not in st.session_state:
    st.session_state["manage_stock_map"] = {}
if "missing_ids" not in st.session_state:
    st.session_state["missing_ids"] = []

col1, col2 = st.columns([1, 1])
with col1:
    refresh_clicked = st.button("Refresh")
with col2:
    update_clicked = st.button("Update")

if refresh_clicked:
    st.session_state["products_df"] = None
    st.session_state["manage_stock_map"] = {}
    st.session_state["missing_ids"] = []

    db = load_item_database()
    if db is None or db.empty:
        st.info("No IDs to fetch from item_database.xlsx.")
    else:
        ids = db["ID"].tolist()
        with st.spinner("Fetching latest data from WooCommerce..."):
            rows, manage_map, missing_ids = fetch_products_for_ids(ids)
            if rows:
                df = pd.DataFrame(rows)
                st.session_state["products_df"] = df
                st.session_state["manage_stock_map"] = manage_map
                st.session_state["missing_ids"] = missing_ids
            else:
                st.info("No products found for the IDs in item_database.xlsx.")

if st.session_state["products_df"] is not None:
    st.subheader("Products (from item_database.xlsx)")
    edited_df = st.data_editor(
        st.session_state["products_df"],
        use_container_width=True,
        column_config={
            "ID": st.column_config.NumberColumn("ID", disabled=True, format="%d"),
            "Parent ID": st.column_config.NumberColumn("Parent ID", disabled=True, format="%d"),
            "Product Name": st.column_config.TextColumn("Product Name", disabled=True),
            "Current Stock": st.column_config.NumberColumn("Current Stock", disabled=True),
            "Sale Price": st.column_config.TextColumn("Sale Price", disabled=True),
            "Regular Price": st.column_config.TextColumn("Regular Price", disabled=True),
            "Type": st.column_config.TextColumn("Type", disabled=True),
            "New Sale Price": st.column_config.TextColumn("New Sale Price", help="Leave blank to skip"),
            "New Stock Quantity": st.column_config.NumberColumn("New Stock Quantity", help="Leave blank to skip"),
        },
        hide_index=True,
        key="product_editor"
    )

    if update_clicked:
        if edited_df is None or edited_df.empty:
            st.info("No rows to update.")
        else:
            updated_count = 0
            failed = []
            stock_not_managed = []

            with st.spinner("Updating products..."):
                for _, row in edited_df.iterrows():
                    prod_id = int(row["ID"])
                    parent_id = row.get("Parent ID")
                    
                    # Check if parent_id is valid (not NaN, None, or empty)
                    parent_missing = (
                        parent_id is None or 
                        (isinstance(parent_id, float) and math.isnan(parent_id)) or 
                        parent_id == ""
                    )
                    
                    new_price = coerce_price(row.get("New Sale Price"))
                    new_stock = coerce_int(row.get("New Stock Quantity"))

                    payload = {}

                    if new_price != "":
                        payload["sale_price"] = new_price

                    if new_stock is not None:
                        manage_stock = bool(st.session_state["manage_stock_map"].get(prod_id, False))
                        if not manage_stock:
                            stock_not_managed.append(prod_id)
                        else:
                            payload["stock_quantity"] = new_stock

                    if not payload:
                        continue

                    # Determine correct API endpoint
                    if parent_missing:
                        target_url = f"{WC_API_URL}/products/{prod_id}"
                    else:
                        target_url = f"{WC_API_URL}/products/{int(parent_id)}/variations/{prod_id}"

                    try:
                        r = requests.put(
                            target_url, 
                            json=payload, 
                            auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET), 
                            timeout=30
                        )
                        if r.status_code in (200, 201):
                            updated_count += 1
                        else:
                            failed.append(f"ID {prod_id} (HTTP {r.status_code}): {r.text[:300]}")
                    except Exception as e:
                        failed.append(f"ID {prod_id} (exception): {str(e)}")

            if updated_count:
                st.success(f"✅ Updated {updated_count} item(s) successfully.")
            if stock_not_managed:
                st.warning(f"⚠️ Stock not managed for ID(s): {', '.join(str(i) for i in sorted(set(stock_not_managed)))}")
            if failed:
                with st.expander("❌ Failed Updates", expanded=True):
                    for error in failed:
                        st.error(error)

if st.session_state["missing_ids"]:
    st.subheader("⚠️ IDs not found on website")
    st.warning(", ".join(str(i) for i in st.session_state["missing_ids"]))
