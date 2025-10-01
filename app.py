import streamlit as st
import pandas as pd
from PyPDF2 import PdfMerger
import os
from pathlib import Path
import io

TOOL_NAME = "MRP Label PDF Merger"

# Cache the PDF folder check to avoid repeated filesystem calls
@st.cache_data
def check_pdf_folder():
    """Check if mrp_label folder exists and return available PDFs"""
    label_folder = Path("mrp_label")
    if label_folder.exists():
        pdf_files = [f.stem for f in label_folder.glob("*.pdf")]
        return True, len(pdf_files), pdf_files
    return False, 0, []

# Cache Excel file reading
@st.cache_data
def load_excel_data(file_bytes, file_name):
    """Load and process Excel file - cached for faster reload"""
    excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
    
    # Check if "Item Summary" sheet exists
    if "Item Summary" not in excel_file.sheet_names:
        return None, f"Sheet 'Item Summary' not found. Available sheets: {', '.join(excel_file.sheet_names)}"
    
    # Read the Item Summary sheet
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Item Summary")
    
    # Create a mapping of lowercase column names to original column names
    column_mapping = {col.lower().strip(): col for col in df.columns}
    
    # Check for required columns (case-insensitive)
    required_columns_lower = ["item id", "variation id", "quantity"]
    required_columns_display = ["Item ID", "Variation ID", "Quantity"]
    
    missing_columns = []
    column_map = {}
    
    for req_col_lower, req_col_display in zip(required_columns_lower, required_columns_display):
        if req_col_lower in column_mapping:
            column_map[req_col_display] = column_mapping[req_col_lower]
        else:
            missing_columns.append(req_col_display)
    
    if missing_columns:
        return None, f"Missing required columns: {', '.join(missing_columns)}"
    
    # Rename columns to standardized names
    rename_dict = {
        column_map["Item ID"]: "Item ID",
        column_map["Variation ID"]: "Variation ID",
        column_map["Quantity"]: "quantity"
    }
    
    # Check if Item Name column exists (case-insensitive)
    item_name_key = None
    for col_lower, col_original in column_mapping.items():
        if "item name" in col_lower:
            item_name_key = col_original
            rename_dict[col_original] = "Item Name"
            break
    
    df = df.rename(columns=rename_dict)
    
    # Remove empty rows
    df = df.dropna(subset=["Item ID", "Variation ID", "quantity"], how='all')
    
    # Create display name for variable products
    if "Item Name" in df.columns:
        df['Display Name'] = df.apply(lambda row: create_display_name(row), axis=1)
    else:
        df['Display Name'] = df.apply(lambda row: f"ID: {int(row['Variation ID']) if pd.notna(row['Variation ID']) and row['Variation ID'] != 0 else int(row['Item ID'])}", axis=1)
    
    return df, None

def create_display_name(row):
    """Create display name based on whether it's a variable product"""
    item_id = row["Item ID"]
    variation_id = row["Variation ID"]
    
    # Check if it's a variable product (variation_id exists and is not 0)
    if pd.notna(variation_id) and variation_id != 0:
        # Variable product - need to extract parent and variation names
        item_name = row.get("Item Name", "")
        
        if pd.notna(item_name) and " - " in str(item_name):
            # Split the item name (assuming format like "Red Capsicum - 250g")
            parts = str(item_name).split(" - ", 1)
            parent_name = parts[0].strip()
            variation_name = parts[1].strip() if len(parts) > 1 else ""
            
            display_name = f"{parent_name} + {variation_name} ({int(item_id)} + {int(variation_id)})"
        else:
            # Fallback if name format is different
            display_name = f"{item_name} ({int(item_id)} + {int(variation_id)})"
    else:
        # Simple product - just use item name and ID
        item_name = row.get("Item Name", f"Item {int(item_id)}")
        display_name = f"{item_name} ({int(item_id)})"
    
    return display_name

st.set_page_config(page_title="MRP Label Merger", page_icon="📄", layout="wide")

st.title("📄 MRP Label PDF Merger")
st.markdown("Upload an Excel file to merge MRP label PDFs based on quantities")

# Initialize session state
if 'uploaded_file_name' not in st.session_state:
    st.session_state.uploaded_file_name = None
if 'df' not in st.session_state:
    st.session_state.df = None
if 'processing_complete' not in st.session_state:
    st.session_state.processing_complete = False

# Display PDF folder status at the top (cached, so very fast)
folder_exists, pdf_count, pdf_list = check_pdf_folder()

col1, col2 = st.columns([3, 1])
with col1:
    if folder_exists:
        st.success(f"✅ PDF Folder Found: {pdf_count} PDF files available")
    else:
        st.error("❌ 'mrp_label' folder not found in current directory!")

with col2:
    if st.button("🔄 Refresh PDF Count"):
        check_pdf_folder.clear()
        st.rerun()

# File uploader
uploaded_file = st.file_uploader("Choose an Excel file (.xlsx)", type=['xlsx'])

if uploaded_file is not None:
    # Check if this is a new file
    if st.session_state.uploaded_file_name != uploaded_file.name:
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.processing_complete = False
        
        # Load data (cached for performance)
        file_bytes = uploaded_file.read()
        df, error = load_excel_data(file_bytes, uploaded_file.name)
        
        if error:
            st.error(f"❌ Error: {error}")
            st.session_state.df = None
        else:
            st.session_state.df = df
            st.success(f"✅ Loaded {len(df)} rows from Excel file")
    
    # Display static data table if loaded
    if st.session_state.df is not None:
        with st.expander("📊 View Loaded Data", expanded=False):
            # Determine which columns to display
            display_cols = ["Display Name", "Item ID", "Variation ID", "quantity"]
            available_cols = [col for col in display_cols if col in st.session_state.df.columns]
            
            st.dataframe(
                st.session_state.df[available_cols],
                use_container_width=True,
                height=300
            )
            
            # Show summary stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Rows", len(st.session_state.df))
            with col2:
                total_qty = st.session_state.df['quantity'].sum()
                st.metric("Total Quantity", int(total_qty))
            with col3:
                unique_ids = st.session_state.df.apply(
                    lambda row: int(row['Variation ID']) if pd.notna(row['Variation ID']) and row['Variation ID'] != 0 else int(row['Item ID']),
                    axis=1
                ).nunique()
                st.metric("Unique IDs", unique_ids)
        
        st.divider()
        
        # Process button
        if st.button("🚀 Process and Merge PDFs", type="primary", use_container_width=True):
            if not folder_exists:
                st.error("❌ Error: 'mrp_label' folder not found!")
                st.stop()
            
            with st.spinner("Processing PDFs..."):
                merger = PdfMerger()
                total_pages = 0
                processed_items = 0
                missing_pdfs = []
                errors = []
                processed_details = []  # Store details for each processed item
                
                label_folder = Path("mrp_label")
                
                # Progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Process each row
                for idx, row in st.session_state.df.iterrows():
                    try:
                        item_id = row["Item ID"]
                        variation_id = row["Variation ID"]
                        quantity = row["quantity"]
                        display_name = row.get("Display Name", "Unknown")
                        
                        # Skip if quantity is 0, NaN, or negative
                        if pd.isna(quantity) or quantity <= 0:
                            continue
                        
                        # Convert to int
                        quantity = int(quantity)
                        
                        # Determine which ID to use
                        if pd.notna(variation_id) and variation_id != 0:
                            use_id = int(variation_id)
                        else:
                            use_id = int(item_id)
                        
                        # PDF file path
                        pdf_path = label_folder / f"{use_id}.pdf"
                        
                        # Check if PDF exists
                        if not pdf_path.exists():
                            missing_pdfs.append(use_id)
                            continue
                        
                        # Merge the PDF 'quantity' times
                        for _ in range(quantity):
                            merger.append(str(pdf_path))
                            total_pages += 1
                        
                        processed_items += 1
                        processed_details.append({
                            'Display Name': display_name,
                            'ID Used': use_id,
                            'Quantity': quantity
                        })
                        
                    except Exception as e:
                        errors.append(f"Row {idx + 2}: {str(e)}")
                    
                    # Update progress
                    progress = (idx + 1) / len(st.session_state.df)
                    progress_bar.progress(progress)
                    status_text.text(f"Processing: {idx + 1}/{len(st.session_state.df)} rows")
                
                progress_bar.empty()
                status_text.empty()
                
                # Generate output filename
                excel_filename = st.session_state.uploaded_file_name.replace('.xlsx', '')
                output_filename = f"mrp_labels_{excel_filename}.pdf"
                
                # Save merged PDF to bytes
                pdf_bytes = io.BytesIO()
                merger.write(pdf_bytes)
                merger.close()
                pdf_bytes.seek(0)
                
                # Store results in session state
                st.session_state.processing_complete = True
                st.session_state.results = {
                    'pdf_bytes': pdf_bytes,
                    'output_filename': output_filename,
                    'processed_items': processed_items,
                    'total_pages': total_pages,
                    'missing_pdfs': missing_pdfs,
                    'errors': errors,
                    'processed_details': processed_details
                }
                
                st.rerun()
        
        # Display results if processing is complete
        if st.session_state.processing_complete:
            results = st.session_state.results
            
            st.success("✅ Processing Complete!")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Items Processed", results['processed_items'])
            with col2:
                st.metric("Total Pages", results['total_pages'])
            with col3:
                st.metric("Missing PDFs", len(results['missing_pdfs']))
            
            # Show processed items details
            if results['processed_details']:
                with st.expander("✅ View Processed Items", expanded=False):
                    processed_df = pd.DataFrame(results['processed_details'])
                    st.dataframe(processed_df, use_container_width=True, height=300)
            
            # Show missing PDFs
            if results['missing_pdfs']:
                st.warning("⚠️ The following Item/Variation IDs were not found:")
                st.code(", ".join(map(str, results['missing_pdfs'])))
            
            # Show errors if any
            if results['errors']:
                with st.expander("❌ View Errors", expanded=False):
                    for error in results['errors']:
                        st.text(error)
            
            # Download button
            if results['total_pages'] > 0:
                st.download_button(
                    label="📥 Download Merged PDF",
                    data=results['pdf_bytes'],
                    file_name=results['output_filename'],
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
            else:
                st.warning("⚠️ No PDFs were merged. Please check your data and PDF files.")

else:
    st.info("👆 Please upload an Excel file to get started")
    
    # Instructions
    with st.expander("📖 Instructions"):
        st.markdown("""
        ### How to use:
        1. **Upload Excel File**: Click the upload button and select your .xlsx file
        2. **Required Sheet**: Make sure your Excel file has a sheet named "Item Summary"
        3. **Required Columns**: 
           - `Item ID`: The item identifier
           - `Variation ID`: The variation identifier (use 0 if no variation)
           - `Quantity`: Number of times to include the label
           - `Item Name`: (Optional) Product name for better display
        4. **PDF Files**: Place all PDF files in a folder named `mrp_label` in the same directory as this script
        5. **File Naming**: PDF files should be named as `{ID}.pdf` (e.g., `7413.pdf`)
        
        ### Logic:
        - If `Variation ID` is 0 or empty, the script uses `Item ID`
        - If `Variation ID` is not 0, the script uses `Variation ID`
        - The corresponding PDF is merged based on the quantity specified
        - **Variable Products**: If Item Name contains " - ", it will display as "Parent + Variation (Parent ID + Variation ID)"
          - Example: "Red Capsicum - 250g" becomes "Red Capsicum + 250g (12625 + 12628)"
        
        ### Output:
        - Merged PDF named: `mrp_labels_{your_excel_filename}.pdf`
        - Summary of processed items and missing PDFs
        """)
