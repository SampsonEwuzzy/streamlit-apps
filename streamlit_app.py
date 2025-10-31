import streamlit as st 
import pandas as pd
from sqlalchemy import create_engine, text
import io 
import os
import re
import difflib

# -------------------------------
# 1️⃣ TRANSFORMATION FUNCTIONS (UPDATED)
# -------------------------------

def transform_attribution_data(file_object: io.BytesIO, file_name: str) -> pd.DataFrame:
    """
    Applies the logic for Attribution/Liability data to a single uploaded file,
    including dropping suspected summary rows.
    """
    try:
        if file_name.endswith(".csv"):
            df = pd.read_csv(file_object, header=3)
        else:
            df = pd.read_excel(file_object, sheet_name='Abuja', header=3)
    except Exception as e:
        st.error(f"❌ Error loading {file_name} for Attribution: {e}")
        return pd.DataFrame()

    hourly_metrics = [
        'FORECAST', 'ACTUAL MW', 'DIFFERENCE', 'DUR OF DISCO OUTAGE',
        'DUR OF TCN OUTAGE', 'DUR OF GENCO OUTAGE',
        'DISCO LIABILITY', 'TCN LIABILITY', 'GENCO LIABILITY'
    ]

    try:
        df.dropna(how='all', inplace=True)
        static_cols = df.columns[:11]
        dynamic_cols = df.columns[11:]

        expected_dynamic_cols = []
        for hour in range(1, 25):
            for metric in hourly_metrics:
                expected_dynamic_cols.append(f"{metric}_{hour}")

        if len(dynamic_cols) != len(expected_dynamic_cols):
             pass 
        
        df.columns = list(static_cols) + expected_dynamic_cols

        # --- Original Row Filtering (removes simple footer/summary rows) ---
        condition_original = (
            df.iloc[:, 8].notna() | df.iloc[:, 9].notna() | df.iloc[:, 10].notna()
        ) & df.iloc[:, :8].isna().all(axis=1)
        df = df[~condition_original].copy()

        # --- NEW ROW FILTERING LOGIC: Remove rows where FORECAST > 500 AND NA count > 5 ---
        
        forecast_col = 'FORECAST_1'
        if forecast_col in df.columns:
            # 1. Convert the 'FORECAST_1' column to numeric (coercing errors)
            df[forecast_col] = pd.to_numeric(df[forecast_col], errors='coerce')

            # 2. Calculate the number of empty (NaN) values in each row across the DataFrame
            na_count = df.isna().sum(axis=1)

            # 3. Define the two combined conditions:
            # Condition A: FORECAST_1 is greater than 500.00
            condition_forecast = df[forecast_col] > 500.00
            
            # Condition B: More than 5 values in the entire row are missing
            condition_na_count = na_count > 5

            # 4. Combine the conditions (AND logic)
            summary_row_condition = condition_forecast & condition_na_count

            # 5. Filter the DataFrame, keeping only rows where the summary condition is NOT TRUE
            df = df[~summary_row_condition].copy()
        
        # --- END NEW FILTERING LOGIC ---

        for metric in hourly_metrics:
            hour_cols = [f"{metric}_{h}" for h in range(1, 25)]
            existing_hour_cols = [col for col in hour_cols if col in df.columns]
            if existing_hour_cols:
                 df[f"{metric}_TOTAL"] = df[existing_hour_cols].sum(axis=1, numeric_only=True)

        df["Source_File"] = os.path.splitext(file_name)[0]
        df["Data_Type"] = "Attribution_Liability"
        
        return df

    except Exception as e:
        st.error(f"❌ Error during Attribution data transformation for {file_name}: {e}")
        return pd.DataFrame()

def transform_outage_data(file_object: io.BytesIO, file_name: str) -> pd.DataFrame:
    """
    Applies the logic for Outage Events data to a single uploaded file.
    """
    expected_columns = [
        "Disco", "Region", "SubRegion/ACC", "Substation", "33kV Feeder",
        "Date off", "Hour Off", "Minute off", "Date on", "Hour On", "Minute on",
        "Duration of Outage (H:mm)", "Class", "Last Load Recorded (MW)", "Event/Indication",
        "Party Responsible", "Name/Designation of Officer Confirming  Interruption (DISCO)",
        "Name/Designation of Officer Confirming  Restoration (DISCO)",
        "Weather Condition", "Remarks"
    ]

    try:
        if file_name.endswith(".csv"):
            df = pd.read_csv(file_object, skiprows=2)
        else:
            df = pd.read_excel(file_object, sheet_name='Abuja Outages', skiprows=2)
    except Exception as e:
        st.error(f"❌ Error loading {file_name} for Outage: {e}")
        return pd.DataFrame()

    try:
        df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)

        col_map = {}
        for expected in expected_columns:
            matches = difflib.get_close_matches(expected, df.columns, n=1, cutoff=0.8)
            if matches:
                col_map[expected] = matches[0]
            else:
                col_map[expected] = None

        clean_df = pd.DataFrame()
        for expected_col in expected_columns:
            actual_col = col_map[expected_col]
            clean_df[expected_col] = df[actual_col] if actual_col in df.columns else None

        clean_df["Duration of Outage (H:mm)"] = clean_df["Duration of Outage (H:mm)"].astype(str).str.strip()

        def duration_to_hours(duration_str):
            try:
                if isinstance(duration_str, float) and duration_str < 1:
                     duration_str = str(pd.Timedelta(seconds=duration_str * 86400))
                
                td = pd.to_timedelta(duration_str) 
                return round(td.total_seconds() / 3600, 2)
            except:
                return None

        clean_df["Outage_Duration_Hours"] = clean_df["Duration of Outage (H:mm)"].apply(duration_to_hours)

        clean_df["Source_File"] = file_name
        clean_df["Data_Type"] = "Outage_Events"
        
        return clean_df

    except Exception as e:
        st.error(f"❌ Error during Outage data transformation for {file_name}: {e}")
        return pd.DataFrame()

# -------------------------------
# 2️⃣ PAGE CONFIG & DB SETUP (UNCHANGED)
# -------------------------------
st.set_page_config(
    page_title="Multi-File Energy Data Uploader (Normalized)",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ Multi-File Energy Data Uploader & Normalized PostgreSQL Save")
st.write("Upload multiple files, transform, review, and save to **two separate tables**.")

# Initialize session state for data and engine
if 'engine' not in st.session_state:
    st.session_state['engine'] = None
if 'df_attr' not in st.session_state:
    st.session_state['df_attr'] = pd.DataFrame()
if 'df_outage' not in st.session_state:
    st.session_state['df_outage'] = pd.DataFrame()
if 'data_processed' not in st.session_state:
    st.session_state['data_processed'] = False

# Database Connection Setup (in sidebar)
st.sidebar.header("Database Connection Settings")
db_user = st.sidebar.text_input("PostgreSQL Username", "postgres")
db_pass = st.sidebar.text_input("Password", type="password")
db_host = st.sidebar.text_input("Host", "localhost")
db_port = st.sidebar.text_input("Port", "5432")
db_name = st.sidebar.text_input("Database Name", "energy_data")

def connect_to_db():
    """Attempts connection and saves engine to session state."""
    try:
        conn_str = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
        st.session_state['engine'] = create_engine(conn_str)
        with st.session_state['engine'].connect() as conn:
            conn.execute(text("SELECT 1"))
        st.sidebar.success("✅ Connected to PostgreSQL!")
    except Exception as e:
        st.session_state['engine'] = None
        st.sidebar.error(f"❌ Connection failed: {e}")

st.sidebar.button("🔗 Connect to Database", on_click=connect_to_db)

# -------------------------------
# 3️⃣ MULTI-FILE UPLOAD & PROCESSING (UNCHANGED)
# -------------------------------

st.subheader("📂 Upload Data Files (Multiple Allowed)")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**File Type 1: Attribution/Liability (Hourly Metrics)**")
    uploaded_files_1 = st.file_uploader(
        "Upload ALL Daily Attribution Reports", 
        key="files1", 
        type=["xlsx", "csv"],
        accept_multiple_files=True
    )

with col2:
    st.markdown("**File Type 2: Outage Events (Event Details)**")
    uploaded_files_2 = st.file_uploader(
        "Upload ALL Outage Events Reports", 
        key="files2", 
        type=["xlsx", "csv"],
        accept_multiple_files=True
    )

if uploaded_files_1 or uploaded_files_2:
    st.divider()
    st.subheader("🛠️ Transformation & Consolidation")

    all_dfs_attr = []
    all_dfs_outage = []

    # Use a button to trigger processing only once
    if st.button("▶️ Process and Consolidate Files"):
        
        # --- PROCESS TYPE 1 ---
        if uploaded_files_1:
            st.markdown("##### Processing Attribution Reports...")
            for file in uploaded_files_1:
                transformed_df = transform_attribution_data(io.BytesIO(file.read()), file.name)
                if not transformed_df.empty:
                    all_dfs_attr.append(transformed_df)

        # --- PROCESS TYPE 2 ---
        if uploaded_files_2:
            st.markdown("##### Processing Outage Reports...")
            for file in uploaded_files_2:
                transformed_df = transform_outage_data(io.BytesIO(file.read()), file.name)
                if not transformed_df.empty:
                    all_dfs_outage.append(transformed_df)

        # --- CONSOLIDATE INTO SEPARATE MASTER TABLES ---
        if all_dfs_attr:
            st.session_state['df_attr'] = pd.concat(all_dfs_attr, ignore_index=True)
            st.success(f"🎉 **Attribution Data Consolidated!** Total rows: **{len(st.session_state['df_attr'])}**")
        else:
            st.session_state['df_attr'] = pd.DataFrame()
        
        if all_dfs_outage:
            st.session_state['df_outage'] = pd.concat(all_dfs_outage, ignore_index=True)
            st.success(f"🎉 **Outage Data Consolidated!** Total rows: **{len(st.session_state['df_outage'])}**")
        else:
            st.session_state['df_outage'] = pd.DataFrame()
            
        st.session_state['data_processed'] = True

else:
    # Clear state if files are removed
    st.session_state['df_attr'] = pd.DataFrame()
    st.session_state['df_outage'] = pd.DataFrame()
    st.session_state['data_processed'] = False

# -------------------------------
# 4️⃣ REVIEW AND SAVE TO DATABASE (UNCHANGED)
# -------------------------------

if st.session_state['data_processed']:
    st.divider()
    st.subheader("👀 Review Data Before Saving")
    
    # --- Review Attribution Data ---
    if not st.session_state['df_attr'].empty:
        df_attr_review = st.session_state['df_attr']
        st.markdown(f"#### Attribution Data Review ({len(df_attr_review)} rows)")
        st.dataframe(df_attr_review.head(), use_container_width=True)

    # --- Review Outage Data ---
    if not st.session_state['df_outage'].empty:
        df_outage_review = st.session_state['df_outage']
        st.markdown(f"#### Outage Data Review ({len(df_outage_review)} rows)")
        st.dataframe(df_outage_review.head(), use_container_width=True)

    st.divider()
    st.subheader("⬇️ Save Consolidated Data to Separate PostgreSQL Tables")

    can_save = st.session_state['engine'] is not None

    if can_save:
        # Save Method Selection (Applies to both)
        save_method = st.radio(
            "How to handle existing tables?",
            ('Replace (overwrite)', 'Append (add rows)', 'Fail (stop if exists)'),
            index=0
        )
        if save_method == 'Replace (overwrite)':
            if_exists_param = 'replace'
        elif save_method == 'Append (add rows)':
            if_exists_param = 'append'
        else:
            if_exists_param = 'fail'
            
        col_save_1, col_save_2 = st.columns(2)
        
        # --- Saving Attribution ---
        if not st.session_state['df_attr'].empty:
            with col_save_1:
                table_name_1 = st.text_input("Table name for Attribution Data:", "attribution_hourly", key="table_attr")
                if st.button("💾 Save Attribution Data"):
                    try:
                        with st.spinner(f'Saving Attribution Data to **{table_name_1}**...'):
                            st.session_state['df_attr'].to_sql(
                                table_name_1, 
                                st.session_state['engine'], 
                                if_exists=if_exists_param, 
                                index=False,
                                chunksize=1000
                            )
                        st.success(f"✅ Attribution Data saved to `{table_name_1}`! ({len(st.session_state['df_attr'])} rows)")
                    except Exception as e:
                        st.error(f"❌ Error saving Attribution Data: {e}")
        
        # --- Saving Outage ---
        if not st.session_state['df_outage'].empty:
            with col_save_2:
                table_name_2 = st.text_input("Table name for Outage Data:", "outage_events_log", key="table_outage")
                if st.button("💾 Save Outage Data"):
                    try:
                        with st.spinner(f'Saving Outage Data to **{table_name_2}**...'):
                            st.session_state['df_outage'].to_sql(
                                table_name_2, 
                                st.session_state['engine'], 
                                if_exists=if_exists_param, 
                                index=False,
                                chunksize=1000
                            )
                        st.success(f"✅ Outage Data saved to `{table_name_2}`! ({len(st.session_state['df_outage'])} rows)")
                    except Exception as e:
                        st.error(f"❌ Error saving Outage Data: {e}")
    else:
        st.warning("⚠️ Connect to the database first (in the sidebar) to enable saving.")

# -------------------------------
# 5️⃣ QUERY AND CALCULATIONS (MODIFIED)
# -------------------------------

if st.session_state['engine'] is not None:
    st.divider()
    st.subheader("📊 Database Analysis & Statistics")
    
    analysis_col1, analysis_col2 = st.columns([1, 2])
    
    with analysis_col1:
        st.markdown("#### Choose Calculation")
        table_to_analyze = st.selectbox(
            "Select Table for Analysis:",
            ("attribution_hourly", "outage_events_log"),
            key="analysis_table"
        )
        
        calculation_type = st.selectbox(
            "Select Calculation Type:",
            ("Total Rows", "Sum of Liability", "Outage Count by Feeder", "Average Outage Duration")
        )
        
        run_analysis = st.button("✨ Run Analysis")

    with analysis_col2:
        st.markdown("#### Results")
        
        if run_analysis:
            try:
                conn = st.session_state['engine'].connect()
                result_df = pd.DataFrame()
                
                if calculation_type == "Total Rows":
                    sql_query = f"SELECT COUNT(*) as total_rows FROM {table_to_analyze};"
                    result = conn.execute(text(sql_query)).scalar()
                    st.metric(label=f"Total Rows in {table_to_analyze}", value=f"{result:,}")
                    
                elif calculation_type == "Sum of Liability" and table_to_analyze == "attribution_hourly":
                    sql_query = """
                        SELECT 
                            SUM("DISCO LIABILITY_TOTAL") AS disco_liability, 
                            SUM("TCN LIABILITY_TOTAL") AS tcn_liability, 
                            SUM("GENCO LIABILITY_TOTAL") AS genco_liability
                        FROM attribution_hourly;
                    """
                    result_df = pd.read_sql(sql_query, conn)
                    st.markdown("##### Total Liabilities (MW-Hours/Duration)")
                    
                    # Display results in Streamlit columns
                    metrics_cols = st.columns(3)
                    if not result_df.empty:
                        metrics_cols[0].metric("DISCO Liability Sum", f"{result_df.iloc[0]['disco_liability']:,.2f}")
                        metrics_cols[1].metric("TCN Liability Sum", f"{result_df.iloc[0]['tcn_liability']:,.2f}")
                        metrics_cols[2].metric("GENCO Liability Sum", f"{result_df.iloc[0]['genco_liability']:,.2f}")
                        
                elif calculation_type == "Outage Count by Feeder" and table_to_analyze == "outage_events_log":
                    sql_query = """
                        SELECT "33kV Feeder", COUNT(*) AS outage_count 
                        FROM outage_events_log 
                        WHERE "33kV Feeder" IS NOT NULL
                        GROUP BY 1 
                        ORDER BY 2 DESC 
                        LIMIT 10;
                    """
                    result_df = pd.read_sql(sql_query, conn)
                    st.markdown("##### Top 10 Feeders by Outage Count")
                    st.dataframe(result_df, use_container_width=True, hide_index=True)
                    st.bar_chart(result_df, x="33kV Feeder", y="outage_count")
                    
                elif calculation_type == "Average Outage Duration" and table_to_analyze == "outage_events_log":
                    sql_query = """
                        SELECT AVG("Outage_Duration_Hours") AS avg_duration 
                        FROM outage_events_log 
                        WHERE "Outage_Duration_Hours" IS NOT NULL;
                    """
                    result = conn.execute(text(sql_query)).scalar()
                    st.metric(label="Average Outage Duration (Hours)", value=f"{result:.2f} hrs")
                    
                else:
                    st.warning(f"Calculation '{calculation_type}' is not applicable to the '{table_to_analyze}' table.")
                    
                conn.close()

            except Exception as e:
                st.error(f"❌ Calculation failed: {e}. Check table names and data types.")
    
    st.divider()
    st.markdown("#### Advanced Query (For Custom Calculations)")
    
    # Custom query area for flexibility
    custom_query = st.text_area(
        "Enter Custom SQL Query (e.g., JOIN tables, date analysis):",
        "SELECT * FROM attribution_hourly LIMIT 5;"
    )

    if st.button("▶️ Run Custom Query"):
        try:
            with st.session_state['engine'].connect() as conn:
                result_df = pd.read_sql(custom_query, conn)
            st.dataframe(result_df, use_container_width=True)
        except Exception as e:
            st.error(f"❌ Query failed: {e}")