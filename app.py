import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="WooCommerce Product Lookup & Update", layout="wide")
st.title("WooCommerce Product Lookup & Update by ID")

# WooCommerce API credentials
WC_API_URL = st.secrets.get("WC_API_URL", "https://sustenance.co.in/wp-json/wc/v3")
WC_CONSUMER_KEY = st.secrets.get("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = st.secrets.get("WC_CONSUMER_SECRET")

# ------------------- FETCH PRODUCT -------------------
st.header("Fetch Product Details")

product_id = st.text_input("Enter Product ID to Fetch:")

if st.button("Fetch Product") and product_id:
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
                "ID": p.get("id"),
                "Parent ID": None,
                "Product Name": p.get("name"),
                "Current Stock": p.get("stock_quantity"),
                "Sale Price": p.get("sale_price"),
                "Regular Price": p.get("regular_price")
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
                        st.warning(f"Error fetching variations for product {p['id']}")
                        break

                    variations = var_resp.json()
                    if not variations:
                        break

                    for v in variations:
                        var_info = {
                            "ID": v.get("id"),
                            "Parent ID": p.get("id"),
                            "Product Name": v.get("name") or p.get("name"),
                            "Current Stock": v.get("stock_quantity"),
                            "Sale Price": v.get("sale_price"),
                            "Regular Price": v.get("regular_price")
                        }
                        all_rows.append(var_info)

                    var_page += 1

            if all_rows:
                df = pd.DataFrame(all_rows)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No product found.")

# ------------------- UPDATE PRODUCT -------------------
st.header("Update Stock & Sale Price")

update_product_id = st.text_input("Enter Product/Variation ID to Update:")
new_stock = st.text_input("Enter New Stock Quantity:")
new_sale_price = st.text_input("Enter New Sale Price (leave blank if no change)")

if st.button("Update Product"):
    if not update_product_id:
        st.error("Please enter a Product/Variation ID to update.")
    else:
        data = {}
        if new_stock:
            try:
                data["stock_quantity"] = int(new_stock)
            except ValueError:
                st.error("Stock must be an integer.")
        if new_sale_price:
            try:
                data["sale_price"] = str(new_sale_price)
            except ValueError:
                st.error("Sale Price must be a number.")

        if data:
            update_resp = requests.put(
                f"{WC_API_URL}/products/{update_product_id}",
                json=data,
                auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
            )

            if update_resp.status_code in [200, 201]:
                st.success(f"Product {update_product_id} updated successfully.")
                st.json(update_resp.json())
            else:
                st.error(f"Failed to update: {update_resp.status_code} - {update_resp.text}")
        else:
            st.info("No changes to update.")
