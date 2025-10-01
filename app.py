import streamlit as st
import requests
import pandas as pd
import math

st.set_page_config(page_title="WooCommerce Product Lookup & Update", layout="wide")
st.title("WooCommerce Product Lookup & Inline Update")

# WooCommerce API credentials
WC_API_URL = st.secrets.get("WC_API_URL", "https://sustenance.co.in/wp-json/wc/v3")
WC_CONSUMER_KEY = st.secrets.get("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = st.secrets.get("WC_CONSUMER_SECRET")

# Guard: secrets required
if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
    st.error("WooCommerce credentials are missing. Please set WC_CONSUMER_KEY and WC_CONSUMER_SECRET in secrets.")
    st.stop()

st.header("Fetch Product Details")

product_id_input = st.text_input("Enter Product ID:")

def is_nan_or_empty(value):
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False

def coerce_int_or_none(value):
    try:
        if is_nan_or_empty(value):
            return None
        return int(float(str(value).strip()))
    except Exception:
        return None

def coerce_price_or_empty(value):
    if is_nan_or_empty(value):
        return ""
    s = str(value).strip()
    if s.lower() == "nan":
        return ""
    return s

@st.cache_data(show_spinner=False)
def load_item_database():
    try:
        df = pd.read_excel("item_database.xlsx")
        if "ID" not in df.columns:
            st.warning("item_database.xlsx does not contain an 'ID' column.")
            return None
        return df
    except FileNotFoundError:
        st.warning("item_database.xlsx not found in the app directory.")
        return None
    except Exception as e:
        st.error(f"Error reading item_database.xlsx: {e}")
        return None

# Session state for table persistence across buttons
if "products_df" not in st.session_state:
    st.session_state["products_df"] = None

fetch_clicked = st.button("Fetch Product")

if fetch_clicked and product_id_input:
    # Validate product ID
    try:
        product_id = int(str(product_id_input).strip())
    except ValueError:
        st.error("Product ID must be an integer.")
        st.stop()

    with st.spinner("Fetching product..."):
        rows = []

        # Fetch base product
        resp = requests.get(
            f"{WC_API_URL}/products/{product_id}",
            auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
        )

        if resp.status_code != 200:
            st.error(f"Error fetching product: {resp.status_code} - {resp.text}")
        else:
            p = resp.json()
            rows.append({
                "ID": p.get("id"),
                "Parent ID": None,
                "Product Name": p.get("name"),
                "Current Stock": p.get("stock_quantity") or 0,
                "Sale Price": p.get("sale_price") or "",
                "Regular Price": p.get("regular_price") or "",
                "Type": p.get("type") or "simple",
            })

            # Fetch variations if variable product
            if p.get("type") == "variable":
                var_page = 1
                while True:
                    vresp = requests.get(
                        f"{WC_API_URL}/products/{p['id']}/variations",
                        params={"per_page": 100, "page": var_page},
                        auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
                    )
                    if vresp.status_code != 200:
                        st.warning(f"Error fetching variations for product {p['id']}: {vresp.status_code} - {vresp.text}")
                        break
                    variations = vresp.json()
                    if not variations:
                        break
                    for v in variations:
                        rows.append({
                            "ID": v.get("id"),
                            "Parent ID": p.get("id"),
                            "Product Name": v.get("name") or p.get("name"),
                            "Current Stock": v.get("stock_quantity") or 0,
                            "Sale Price": v.get("sale_price") or "",
                            "Regular Price": v.get("regular_price") or "",
                            "Type": v.get("type") or "variation",
                        })
                    var_page += 1

            # Build DataFrame with read-only current columns + two editable input columns
            df = pd.DataFrame(rows, columns=[
                "ID", "Parent ID", "Product Name", "Current Stock", "Sale Price", "Regular Price", "Type"
            ])
            # Add editable input columns (text boxes)
            df["New Sale Price"] = ""
            df["New Stock Quantity"] = ""

            st.session_state["products_df"] = df

# Render editor if we have data
if st.session_state["products_df"] is not None:
    st.subheader("Product Table")
    edited_df = st.data_editor(
        st.session_state["products_df"],
        use_container_width=True,
        column_config={
            "ID": st.column_config.TextColumn("ID"),
            "Parent ID": st.column_config.TextColumn("Parent ID"),
            "Product Name": st.column_config.TextColumn("Product Name"),
            "Current Stock": st.column_config.TextColumn("Current Stock"),
            "Sale Price": st.column_config.TextColumn("Sale Price"),
            "Regular Price": st.column_config.TextColumn("Regular Price"),
            "Type": st.column_config.TextColumn("Type"),
            "New Sale Price": st.column_config.TextColumn("New Sale Price", help="Leave blank to skip price update"),
            "New Stock Quantity": st.column_config.TextColumn("New Stock Quantity", help="Leave blank to skip stock update"),
        },
        disabled=["ID", "Parent ID", "Product Name", "Current Stock", "Sale Price", "Regular Price", "Type"],
    )

    # Static table from item_database.xlsx, matched by ID
    db_df = load_item_database()
    if db_df is not None and edited_df is not None and not edited_df.empty:
        try:
            product_ids = edited_df["ID"].astype(str)
            db_ids = db_df["ID"].astype(str)
            static_subset = db_df[db_ids.isin(product_ids)].copy()

            st.subheader("Item Database (from item_database.xlsx)")
            st.dataframe(static_subset, use_container_width=True)
        except Exception as e:
            st.error(f"Error displaying item database: {e}")

    # Update button
    if st.button("Update"):
        to_update = edited_df.copy()
        if to_update.empty:
            st.info("No rows to update.")
        else:
            updated = 0
            failed = []

            for _, row in to_update.iterrows():
                new_price = coerce_price_or_empty(row.get("New Sale Price"))
                new_stock = coerce_int_or_none(row.get("New Stock Quantity"))

                payload = {}

                # Only include fields user provided
                if new_price != "":
                    payload["sale_price"] = new_price
                if new_stock is not None:
                    payload["manage_stock"] = True
                    payload["stock_quantity"] = new_stock

                # Skip if nothing to update
                if not payload:
                    continue

                # Choose correct endpoint (variation vs product)
                parent_id = row.get("Parent ID")
                is_parent_missing = (
                    parent_id is None or
                    (isinstance(parent_id, float) and math.isnan(parent_id)) or
                    parent_id == ""
                )
                target_url = (
                    f"{WC_API_URL}/products/{int(row['ID'])}"
                    if is_parent_missing
                    else f"{WC_API_URL}/products/{int(parent_id)}/variations/{int(row['ID'])}"
                )

                resp = requests.put(target_url, json=payload, auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET))

                if resp.status_code in (200, 201):
                    updated += 1
                else:
                    failed.append(f"ID {row['ID']} (HTTP {resp.status_code}): {resp.text[:300]}")

            if updated:
                st.success(f"Updated {updated} item(s) successfully.")
            if failed:
                st.error("Some updates failed:\n" + "\n".join(failed))
