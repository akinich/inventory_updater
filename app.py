I'll outline the tasks to update your Streamlit app (variation endpoint, editor config, selection, safe coercion, manage_stock, validation, secrets check, and improved errors), then implement all changes in the revised code.

[1 tool called]

I’m going to implement all requested fixes in your Streamlit code: correct variation update endpoint, configure the data editor properly with disabled columns, add a selection checkbox, safely coerce values, ensure stock management is enabled when updating stock, validate the product ID, verify secrets are present, and improve error messages.

[1 tool called]

- I validated secrets, product ID input, corrected the variation update endpoint, switched to `column_config` with disabled columns, added a selection column, added safe coercion for numbers/empties, set `manage_stock` when updating stock, and improved error reporting.

Here’s the revised code. It keeps your structure but fixes the issues:

```python
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

# Secrets validation
if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
    st.error("WooCommerce credentials are missing. Please set WC_CONSUMER_KEY and WC_CONSUMER_SECRET in secrets.")
    st.stop()

# ------------------- FETCH PRODUCT -------------------
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
        return int(float(value))
    except Exception:
        return None

def coerce_price_or_empty(value):
    if is_nan_or_empty(value):
        return ""
    s = str(value).strip()
    if s.lower() == "nan":
        return ""
    return s

if st.button("Fetch Product") and product_id_input:
    # Validate product ID
    try:
        product_id = int(str(product_id_input).strip())
    except ValueError:
        st.error("Product ID must be an integer.")
        st.stop()

    with st.spinner("Fetching product..."):
        all_rows = []

        # Fetch base product
        response = requests.get(
            f"{WC_API_URL}/products/{product_id}",
            auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
        )

        if response.status_code != 200:
            st.error(f"Error fetching product: {response.status_code} - {response.text}")
        else:
            p = response.json()
            base_info = {
                "Update?": True,
                "ID": p.get("id"),
                "Parent ID": None,
                "Product Name": p.get("name"),
                "Current Stock": p.get("stock_quantity") or 0,
                "Sale Price": p.get("sale_price") or "",
                "Regular Price": p.get("regular_price") or "",
                "Type": p.get("type"),
                "Manage Stock": bool(p.get("manage_stock")),
            }
            all_rows.append(base_info)

            # Fetch variations if variable product
            if p.get("type") == "variable":
                var_page = 1
                while True:
                    var_resp = requests.get(
                        f"{WC_API_URL}/products/{p['id']}/variations",
                        params={"per_page": 100, "page": var_page},
                        auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
                    )

                    if var_resp.status_code != 200:
                        st.warning(f"Error fetching variations for product {p['id']}: {var_resp.status_code} - {var_resp.text}")
                        break

                    variations = var_resp.json()
                    if not variations:
                        break

                    for v in variations:
                        var_info = {
                            "Update?": True,
                            "ID": v.get("id"),
                            "Parent ID": p.get("id"),
                            "Product Name": v.get("name") or p.get("name"),
                            "Current Stock": v.get("stock_quantity") or 0,
                            "Sale Price": v.get("sale_price") or "",
                            "Regular Price": v.get("regular_price") or "",
                            "Type": v.get("type") or "variation",
                            "Manage Stock": bool(v.get("manage_stock")),
                        }
                        all_rows.append(var_info)

                    var_page += 1

            if all_rows:
                df = pd.DataFrame(all_rows)

                st.subheader("Product Table (Edit Stock & Sale Price)")
                edited_df = st.data_editor(
                    df,
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config={
                        "Update?": st.column_config.CheckboxColumn("Update?", help="Uncheck to skip updating this row"),
                        "ID": st.column_config.TextColumn("ID"),
                        "Parent ID": st.column_config.TextColumn("Parent ID"),
                        "Product Name": st.column_config.TextColumn("Product Name"),
                        "Regular Price": st.column_config.TextColumn("Regular Price"),
                        "Current Stock": st.column_config.NumberColumn("Current Stock"),
                        "Sale Price": st.column_config.TextColumn("Sale Price"),
                        "Type": st.column_config.TextColumn("Type"),
                        "Manage Stock": st.column_config.CheckboxColumn("Manage Stock"),
                    },
                    disabled=["ID", "Parent ID", "Product Name", "Regular Price", "Type"],
                )

                # ------------------- UPDATE PRODUCTS -------------------
                if st.button("Update Selected Products"):
                    rows_to_update = edited_df[edited_df["Update?"] == True]
                    if rows_to_update.empty:
                        st.info("No rows selected for update.")
                    else:
                        updated_count = 0
                        failed = []

                        for _, row in rows_to_update.iterrows():
                            stock_val = coerce_int_or_none(row.get("Current Stock"))
                            sale_price_val = coerce_price_or_empty(row.get("Sale Price"))
                            manage_stock_val = bool(row.get("Manage Stock"))

                            product_data = {}

                            if stock_val is not None:
                                product_data["manage_stock"] = True if manage_stock_val or stock_val is not None else False
                                product_data["stock_quantity"] = stock_val

                            if sale_price_val != "":
                                product_data["sale_price"] = sale_price_val
                            else:
                                # Send empty string to clear sale price explicitly
                                product_data["sale_price"] = ""

                            # Choose endpoint: product vs variation
                            parent_id = row.get("Parent ID")
                            target_url = (
                                f"{WC_API_URL}/products/{int(row['ID'])}"
                                if pd.isna(parent_id) or parent_id in (None, "")
                                else f"{WC_API_URL}/products/{int(parent_id)}/variations/{int(row['ID'])}"
                            )

                            resp = requests.put(
                                target_url,
                                json=product_data,
                                auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
                            )

                            if resp.status_code in [200, 201]:
                                updated_count += 1
                            else:
                                failed.append(
                                    f"ID {row['ID']} (HTTP {resp.status_code}): {resp.text[:300]}"
                                )

                        if updated_count:
                            st.success(f"Updated {updated_count} product(s) successfully!")
                        if failed:
                            st.error("Some updates failed:\n" + "\n".join(failed))
            else:
                st.info("No product found.")
```

- All tasks have been completed and reflected in the code.
