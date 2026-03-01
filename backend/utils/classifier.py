import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from schemas import CustomerCategory
import io
import re

try:
    import PyPDF2
    import pdfplumber
except ImportError:
    PyPDF2 = None
    pdfplumber = None


def detect_columns(file_content: bytes, filename: str) -> List[str]:
    """
    Detect column headers from uploaded file.
    
    Returns:
        List of column names found in the file
    """
    filename_lower = filename.lower()
    
    try:
        if filename_lower.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content), nrows=0)
        elif filename_lower.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file_content), nrows=0)
        elif filename_lower.endswith('.pdf'):
            if not pdfplumber:
                raise ValueError("PDF support not available")
            df = _parse_pdf_file(file_content)
        else:
            raise ValueError("Unsupported file format")
        
        return df.columns.tolist()
    except Exception as e:
        raise ValueError(f"Failed to detect columns: {str(e)}")


def classify_customers_dynamic(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
    percentile: int = 70
) -> tuple[pd.DataFrame, Dict[str, int], Dict[str, Any]]:
    """
    Classify customers based on DYNAMIC thresholds using percentiles.
    
    Args:
        df: DataFrame with customer data
        column_mapping: Map of standard names to actual column names
            e.g., {"name": "Customer_Name", "phone": "Mobile_No"}
        percentile: Percentile to use for threshold (default 70)
    
    Logic:
        - Calculate 70th percentile for purchase_count and total_quantity
        - High Frequency = purchase_count >= percentile threshold
        - High Bulk = total_quantity >= percentile threshold
        - Segmentation:
            * High Frequency + High Bulk = "both" (VIP)
            * High Frequency only = "frequent_customer"
            * High Bulk only = "bulk_buyer"
            * Low both = "regular"
    """
    # Apply column mapping if provided
    if column_mapping:
        df = df.rename(columns={v: k for k, v in column_mapping.items() if v in df.columns})
    
    # Handle field name variations (frontend uses different names)
    # quantity -> total_quantity
    if 'quantity' in df.columns and 'total_quantity' not in df.columns:
        df['total_quantity'] = df['quantity']
    
    # total_spent -> order_value
    if 'total_spent' in df.columns and 'order_value' not in df.columns:
        df['order_value'] = df['total_spent']
    
    # Ensure required columns exist with defaults
    if 'total_quantity' not in df.columns:
        df['total_quantity'] = 0
    
    if 'purchase_count' not in df.columns:
        df['purchase_count'] = 1
    
    if 'order_value' not in df.columns:
        df['order_value'] = 0
    
    # CRITICAL: Convert to numeric types to avoid string division errors
    df['total_quantity'] = pd.to_numeric(df['total_quantity'], errors='coerce').fillna(0)
    df['purchase_count'] = pd.to_numeric(df['purchase_count'], errors='coerce').fillna(1)
    df['order_value'] = pd.to_numeric(df['order_value'], errors='coerce').fillna(0)
    
    # Ensure purchase_count is at least 1 to avoid division by zero
    df['purchase_count'] = df['purchase_count'].replace(0, 1)
    
    # Calculate average items per order (for bulk detection)
    df['avg_items_per_order'] = df['total_quantity'] / df['purchase_count']
    
    # Calculate DYNAMIC thresholds based on percentiles
    freq_threshold = np.percentile(df['purchase_count'].dropna(), percentile)
    bulk_threshold = np.percentile(df['avg_items_per_order'].dropna(), percentile)
    
    # Alternative: Use total_quantity if avg_items_per_order is not meaningful
    if df['avg_items_per_order'].max() < 2:  # If data doesn't have meaningful order splits
        bulk_threshold = np.percentile(df['total_quantity'].dropna(), percentile)
        use_total_qty = True
    else:
        use_total_qty = False
    
    # Classification logic with dynamic thresholds
    def classify_row(row):
        is_frequent = row.get('purchase_count', 0) >= freq_threshold
        
        if use_total_qty:
            is_bulk = row.get('total_quantity', 0) >= bulk_threshold
        else:
            is_bulk = row.get('avg_items_per_order', 0) >= bulk_threshold
        
        if is_frequent and is_bulk:
            return CustomerCategory.BOTH.value
        elif is_frequent:
            return CustomerCategory.FREQUENT_CUSTOMER.value
        elif is_bulk:
            return CustomerCategory.BULK_BUYER.value
        else:
            return CustomerCategory.REGULAR.value
    
    df['category'] = df.apply(classify_row, axis=1)
    df['segment'] = df['category']  # Add segment column for consistency
    
    # Calculate classification counts
    classifications = df['category'].value_counts().to_dict()
    
    # Add threshold info for transparency
    thresholds = {
        'frequency_threshold': float(freq_threshold),
        'bulk_threshold': float(bulk_threshold),
        'metric_used': 'total_quantity' if use_total_qty else 'avg_items_per_order',
        'percentile': percentile
    }
    
    return df, classifications, thresholds


def classify_customers(df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, int]]:
    """
    Backward-compatible classification function using fixed thresholds.
    For new implementations, use classify_customers_dynamic().
    """
    df_result, classifications, _ = classify_customers_dynamic(df, None, 70)
    return df_result, classifications


def parse_csv_file(
    file_content: bytes,
    filename: str,
    column_mapping: Optional[Dict[str, str]] = None
) -> pd.DataFrame:
    """
    Parse uploaded CSV/Excel/PDF file and extract customer data.
    
    Args:
        file_content: Raw file bytes
        filename: Original filename
        column_mapping: User-provided mapping of their columns to standard names
            e.g., {"name": "Customer_Full_Name", "phone": "Mobile_No"}
    """
    filename_lower = filename.lower()
    
    if filename_lower.endswith('.csv'):
        df = pd.read_csv(io.BytesIO(file_content))
    
    elif filename_lower.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(io.BytesIO(file_content))
    
    elif filename_lower.endswith('.pdf'):
        if not pdfplumber:
            raise ValueError("PDF support not available. Please install pdfplumber.")
        df = _parse_pdf_file(file_content)
    
    else:
        raise ValueError("Unsupported file format. Please upload CSV, Excel (.xlsx, .xls) or PDF file.")
    
    # If user provided column mapping, use it
    if column_mapping:
        # Apply user's column mapping
        df = df.rename(columns={v: k for k, v in column_mapping.items() if v in df.columns})
    else:
        # Standardize column names
        df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')
        
        # Map common column variations to standard names (auto-detection)
        auto_mapping = {
            'customer_name': 'name',
            'customer': 'name',
            'full_name': 'name',
            'phone_number': 'phone',
            'mobile': 'phone',
            'contact': 'phone',
            'email_address': 'email',
            'quantity': 'total_quantity',
            'qty': 'total_quantity',
            'orders': 'purchase_count',
            'order_count': 'purchase_count',
            'amount': 'order_value',
            'total_amount': 'order_value',
            'value': 'order_value',
        }
        
        df.rename(columns=auto_mapping, inplace=True)
    
    # Validate required columns
    required_cols = ['name', 'phone']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {', '.join(missing_cols)}. "
            f"Available columns: {', '.join(df.columns.tolist())}"
        )
    
    # Clean phone numbers - remove spaces, dashes, parentheses
    if 'phone' in df.columns:
        df['phone'] = df['phone'].astype(str).str.replace(r'[\s\-\(\)]', '', regex=True)
    
    # Fill missing values
    if 'email' not in df.columns:
        df['email'] = ''
    
    # Handle both frontend and backend field naming conventions
    if 'total_quantity' not in df.columns and 'quantity' not in df.columns:
        df['total_quantity'] = 0
    
    if 'purchase_count' not in df.columns:
        df['purchase_count'] = 1
    
    if 'order_value' not in df.columns and 'total_spent' not in df.columns:
        df['order_value'] = 0
    
    # CRITICAL: Convert numeric columns to proper types (handle both naming conventions)
    numeric_columns = ['total_quantity', 'quantity', 'purchase_count', 'order_value', 'total_spent']
    for col in numeric_columns:
        if col in df.columns:
            # Different default values based on column type
            if col == 'purchase_count':
                default_val = 1
            else:
                default_val = 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(default_val)
    
    return df


def _parse_pdf_file(file_content: bytes) -> pd.DataFrame:
    """
    Extract tabular data from PDF file.
    """
    if not pdfplumber:
        raise ValueError("pdfplumber library not installed")
    
    try:
        # Try using pdfplumber to extract tables
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            all_tables = []
            
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 1:  # Has header and data
                        # Convert to DataFrame
                        df_table = pd.DataFrame(table[1:], columns=table[0])
                        all_tables.append(df_table)
            
            if not all_tables:
                raise ValueError("No tables found in PDF")
            
            # Combine all tables
            df = pd.concat(all_tables, ignore_index=True)
            
            # Clean up None values
            df = df.fillna('')
            
            return df
    
    except Exception as e:
        # Fallback: Try to extract text and parse
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                text = ''
                for page in pdf.pages:
                    text += page.extract_text() + '\n'
                
                # Try to parse text as CSV-like data
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                
                if len(lines) < 2:
                    raise ValueError("PDF does not contain enough data")
                
                # Assume first line is header
                header = re.split(r'\s{2,}|\t', lines[0])
                data = []
                
                for line in lines[1:]:
                    row = re.split(r'\s{2,}|\t', line)
                    if len(row) == len(header):
                        data.append(row)
                
                if not data:
                    raise ValueError("Could not parse PDF data")
                
                df = pd.DataFrame(data, columns=header)
                return df
        
        except Exception as parse_error:
            raise ValueError(
                f"Failed to extract data from PDF: {str(parse_error)}. "
                "Please ensure the PDF contains a table with customer data."
            )

def prepare_message(template: str, customer_data: Dict[str, Any]) -> str:
    """
    Replace placeholders in message template with customer data.
    """
    message = template
    for key, value in customer_data.items():
        placeholder = f"{{{{{key}}}}}"
        message = message.replace(placeholder, str(value))
    return message
