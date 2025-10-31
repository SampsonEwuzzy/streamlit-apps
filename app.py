import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import requests
import io
from PIL import Image # Import the Pillow library

# --- APP CONFIGURATION ---
st.set_page_config(page_title="PDF Content Extractor", layout="wide")
st.title("PDF Content Extractor (Web OCR)")
st.info("Upload any PDF to extract all text content using a powerful web-based OCR engine.")
st.warning("ℹ️ This app requires an internet connection to process documents.")

# --- HELPER FUNCTIONS ---
def extract_content_with_web_ocr(file_bytes):
    """
    Uses PyMuPDF to get images of pages, compresses them, and sends them to the ocr.space API.
    Args:
        file_bytes: The PDF file in bytes.
    Returns:
        A single pandas DataFrame containing all extracted text.
    """
    full_text = ""
    # The URL of the free OCR API
    OCR_API_URL = 'https://api.ocr.space/parse/image'
    
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page_num, page in enumerate(doc):
            st.write(f"Processing page {page_num + 1}...")
            # Convert the page to an image (pixmap)
            pix = page.get_pixmap(dpi=200) # Use a reasonable DPI
            
            try:
                # --- NEW IMAGE COMPRESSION STEP ---
                # Convert the pixmap to a Pillow Image object
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                
                # Create an in-memory byte stream to save the compressed image
                output_buffer = io.BytesIO()
                
                # Save the image as a JPEG with a quality of 85.
                # This significantly reduces file size while maintaining readability.
                img.save(output_buffer, format="JPEG", quality=85)
                
                # Get the compressed image bytes
                img_bytes = output_buffer.getvalue()
                
                # --- END OF NEW STEP ---

                # Prepare the request to the OCR API with the compressed JPEG image
                payload = {'isOverlayRequired': False, 'apikey': 'helloworld', 'language': 'eng'}
                files = {'file': (f'page_{page_num}.jpeg', img_bytes, 'image/jpeg')}
                
                # Send the request
                response = requests.post(OCR_API_URL, files=files, data=payload)
                response.raise_for_status() # Raise an exception for bad status codes
                
                result = response.json()
                
                if result.get('IsErroredOnProcessing'):
                    st.error(f"OCR API Error on page {page_num + 1}: {result.get('ErrorMessage')}")
                    continue
                
                # Extract the parsed text
                parsed_text = result.get('ParsedResults', [{}])[0].get('ParsedText', '')
                full_text += parsed_text + f"\n\n--- End of Page {page_num + 1} ---\n\n"

            except requests.exceptions.RequestException as e:
                st.error(f"Network error while processing page {page_num + 1}: {e}")
                return pd.DataFrame() # Stop processing on network error
            except Exception as e:
                st.warning(f"Could not process page {page_num + 1} with Web OCR. Error: {e}")

    # Split the full text into lines and create a DataFrame
    lines = full_text.strip().split('\n')
    df = pd.DataFrame(lines, columns=["Extracted Content"])
    return df

def dataframe_to_excel_bytes(df):
    """Converts a pandas DataFrame to an in-memory Excel file (bytes)."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Extracted_Content')
    return output.getvalue()

@st.cache_data
def dataframe_to_csv_bytes(df):
    """Converts a pandas DataFrame to an in-memory CSV file (bytes)."""
    return df.to_csv(index=False).encode('utf-8')

# --- Initialize Session State ---
if 'extracted_df' not in st.session_state:
    st.session_state.extracted_df = None

# --- STEP 1: UPLOAD PDF ---
st.header("Step 1: Upload Your PDF")
uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    # Use a spinner to show progress
    with st.spinner("Sending pages to Web OCR... This can take some time depending on document length."):
        extracted_df = extract_content_with_web_ocr(uploaded_file.getvalue())
        st.session_state.extracted_df = extracted_df
        
        if extracted_df.empty:
            st.warning("No text content could be extracted from this PDF.")
        else:
            st.success("Successfully extracted all text content!")

# --- STEP 2: VIEW AND DOWNLOAD EXTRACTED CONTENT ---
if st.session_state.extracted_df is not None and not st.session_state.extracted_df.empty:
    st.header("Step 2: View and Download Extracted Content")

    st.dataframe(st.session_state.extracted_df)
    
    excel_bytes = dataframe_to_excel_bytes(st.session_state.extracted_df)
    csv_bytes = dataframe_to_csv_bytes(st.session_state.extracted_df)
    
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            label="📥 Download Content as Excel",
            data=excel_bytes,
            file_name=f"{uploaded_file.name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="excel_btn"
        )
    
    with col2:
        st.download_button(
            label="📥 Download Content as CSV",
            data=csv_bytes,
            file_name=f"{uploaded_file.name}.csv",
            mime="text/csv",
            key="csv_btn"
        )

