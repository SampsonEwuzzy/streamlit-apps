import streamlit as st
import pandas as pd
from io import BytesIO

# ------------------------------------------------------------
# 1️⃣ PAGE CONFIG
# ------------------------------------------------------------
st.set_page_config(
    page_title="Excel Multi-File & Multi-Sheet Consolidator",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Excel Multi-File & Multi-Sheet Consolidator & Analyzer")
st.write(
    "Upload one or more Excel files (.xlsx or .xls). "
    "This app will read all sheets in each file, consolidate them into one dataset, "
    "add 'Source_File' and 'Source_Sheet' columns, and allow quick analysis and download."
)

# ------------------------------------------------------------
# 2️⃣ MULTI-FILE UPLOAD
# ------------------------------------------------------------
uploaded_files = st.file_uploader(
    "📂 Upload one or more Excel files", 
    type=["xlsx", "xls"], 
    accept_multiple_files=True
)

if uploaded_files:
    try:
        consolidated_df = pd.DataFrame()
        file_count = 0
        sheet_count = 0

        # Loop through uploaded Excel files
        for uploaded_file in uploaded_files:
            file_count += 1
            all_sheets = pd.read_excel(uploaded_file, sheet_name=None)
            
            for sheet_name, df in all_sheets.items():
                sheet_count += 1
                df["Source_File"] = uploaded_file.name
                df["Source_Sheet"] = sheet_name
                consolidated_df = pd.concat([consolidated_df, df], ignore_index=True)

        st.success(f"✅ Consolidated {sheet_count} sheets from {file_count} files ({len(consolidated_df)} rows).")

        # ------------------------------------------------------------
        # Handle timedelta columns
        # ------------------------------------------------------------
        for col in consolidated_df.select_dtypes(include=["timedelta"]).columns:
            consolidated_df[col] = consolidated_df[col].dt.total_seconds() / 3600  # convert to hours

        # ------------------------------------------------------------
        # Show preview
        # ------------------------------------------------------------
        st.dataframe(consolidated_df.head(), use_container_width=True)

        # ------------------------------------------------------------
        # 3️⃣ BASIC ANALYSIS
        # ------------------------------------------------------------
        st.divider()
        st.subheader("🔍 Quick Data Analysis")

        numeric_cols = consolidated_df.select_dtypes(include=["number"]).columns.tolist()
        date_cols = consolidated_df.select_dtypes(include=["datetime64"]).columns.tolist()

        col1, col2 = st.columns(2)

        with col1:
            if numeric_cols:
                selected_num_col = st.selectbox("Select numeric column for summary statistics:", numeric_cols)
                if selected_num_col:
                    stats = consolidated_df[selected_num_col].describe()
                    st.write("**Summary Statistics:**")
                    st.write(stats)

                    st.metric("Sum", f"{consolidated_df[selected_num_col].sum():,.2f}")
                    st.metric("Mean", f"{consolidated_df[selected_num_col].mean():,.2f}")
                    st.metric("Max", f"{consolidated_df[selected_num_col].max():,.2f}")
                    st.metric("Min", f"{consolidated_df[selected_num_col].min():,.2f}")
            else:
                st.warning("No numeric columns found for analysis.")

        with col2:
            if date_cols:
                selected_date_col = st.selectbox("Select date column for analysis:", date_cols)
                if selected_date_col:
                    st.write("**Date Range:**")
                    st.write(
                        f"From: {consolidated_df[selected_date_col].min()}  \n"
                        f"To: {consolidated_df[selected_date_col].max()}"
                    )
            else:
                st.info("No date columns detected in dataset.")

        # ------------------------------------------------------------
        # 4️⃣ DOWNLOAD CONSOLIDATED DATA
        # ------------------------------------------------------------
        st.divider()
        st.subheader("⬇️ Download Consolidated File")

        download_format = st.radio("Select download format:", ["Excel (.xlsx)", "CSV (.csv)"])

        if download_format == "CSV (.csv)":
            csv_data = consolidated_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Download Consolidated CSV",
                data=csv_data,
                file_name="consolidated_data.csv",
                mime="text/csv"
            )
        else:
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                consolidated_df.to_excel(writer, index=False, sheet_name="Consolidated")

            st.download_button(
                label="💾 Download Consolidated Excel File",
                data=output.getvalue(),
                file_name="consolidated_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"❌ Error reading file(s): {e}")

else:
    st.info("👆 Please upload one or more Excel files to begin.")
