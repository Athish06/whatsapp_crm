import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from schemas import CustomerCategory
import io
import re
from scipy import stats

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


def classify_customers_rfm(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
    today: Optional[pd.Timestamp] = None
) -> tuple[pd.DataFrame, Dict[str, int], Dict[str, Any]]:
    """
    Hybrid RFM Segmentation with Log Transform + Z-Score + Quintile Scoring.
    
    Args:
        df: DataFrame with customer data
        column_mapping: Map of standard names to actual column names
        today: Reference date for recency calculation (defaults to today)
    
    RFM Logic:
        1. Calculate R (recency in days), F (frequency), M (monetary)
        2. Log transform: log(x+1) to handle outliers
        3. Z-score scaling: standardize to mean=0
        4. Quintile scoring: divide into 5 groups, score 1-5
        5. Total RFM Score = R_Score + F_Score + M_Score (3-15)
        6. Segment mapping:
           - 12-15: Both (VIP/Champion)
           - 8-11: Frequent/Loyal
           - 5-7: Bulk/Potential
           - 3-4: Regular/At-Risk
    """
    # Apply column mapping if provided
    if column_mapping:
        df = df.rename(columns={v: k for k, v in column_mapping.items() if v in df.columns})
    
    # Handle field name variations
    if 'quantity' in df.columns and 'total_quantity' not in df.columns:
        df['total_quantity'] = df['quantity']
    if 'total_spent' in df.columns and 'order_value' not in df.columns:
        df['order_value'] = df['total_spent']
    
    # Ensure required columns exist with defaults
    if 'purchase_count' not in df.columns:
        df['purchase_count'] = 1
    if 'order_value' not in df.columns:
        df['order_value'] = 0
    if 'last_transaction_date' not in df.columns:
        df['last_transaction_date'] = pd.Timestamp.now()
    
    # Convert to numeric types
    df['purchase_count'] = pd.to_numeric(df['purchase_count'], errors='coerce').fillna(1).replace(0, 1)
    df['order_value'] = pd.to_numeric(df['order_value'], errors='coerce').fillna(0)
    
    # Parse last transaction date
    if today is None:
        today = pd.Timestamp.now()
    
    df['last_transaction_date'] = pd.to_datetime(df['last_transaction_date'], errors='coerce')
    df['last_transaction_date'] = df['last_transaction_date'].fillna(today)
    
    # ==== STEP 1: Calculate RFM Metrics ====
    df['recency'] = (today - df['last_transaction_date']).dt.days
    df['recency'] = df['recency'].clip(lower=0)  # Ensure non-negative
    df['frequency'] = df['purchase_count']
    df['monetary'] = df['order_value']
    
    # ==== STEP 2: Log Transform + Z-Score Scaling ====
    # Log transform to handle outliers
    df['recency_log'] = np.log1p(df['recency'])  # log(x+1)
    df['frequency_log'] = np.log1p(df['frequency'])
    df['monetary_log'] = np.log1p(df['monetary'])
    
    # Z-score normalization (mean=0, std=1) - handle edge cases
    try:
        df['recency_scaled'] = stats.zscore(df['recency_log'])
        df['frequency_scaled'] = stats.zscore(df['frequency_log'])
        df['monetary_scaled'] = stats.zscore(df['monetary_log'])
    except:
        # If std is 0 (all values same), use 0
        df['recency_scaled'] = 0
        df['frequency_scaled'] = 0
        df['monetary_scaled'] = 0
    
    # ==== STEP 3: Quintile Scoring (1-5) ====
    # For Recency: LOWER is BETTER (recent customers score higher)
    try:
        df['r_score'] = pd.qcut(df['recency'], q=5, labels=[5, 4, 3, 2, 1], duplicates='drop')
        df['r_score'] = df['r_score'].astype(int)
    except (ValueError, TypeError):
        # Fallback: use percentile-based scoring for small/uniform datasets
        df['r_score'] = pd.cut(df['recency'], bins=5, labels=[5, 4, 3, 2, 1], duplicates='drop', include_lowest=True)
        if df['r_score'].isna().all():
            df['r_score'] = 3  # Default mid-range score
        else:
            df['r_score'] = df['r_score'].fillna(3).astype(int)
    
    # For Frequency: HIGHER is BETTER
    try:
        df['f_score'] = pd.qcut(df['frequency'], q=5, labels=[1, 2, 3, 4, 5], duplicates='drop')
        df['f_score'] = df['f_score'].astype(int)
    except (ValueError, TypeError):
        df['f_score'] = pd.cut(df['frequency'], bins=5, labels=[1, 2, 3, 4, 5], duplicates='drop', include_lowest=True)
        if df['f_score'].isna().all():
            df['f_score'] = 3
        else:
            df['f_score'] = df['f_score'].fillna(3).astype(int)
    
    # For Monetary: HIGHER is BETTER
    try:
        df['m_score'] = pd.qcut(df['monetary'], q=5, labels=[1, 2, 3, 4, 5], duplicates='drop')
        df['m_score'] = df['m_score'].astype(int)
    except (ValueError, TypeError):
        df['m_score'] = pd.cut(df['monetary'], bins=5, labels=[1, 2, 3, 4, 5], duplicates='drop', include_lowest=True)
        if df['m_score'].isna().all():
            df['m_score'] = 3
        else:
            df['m_score'] = df['m_score'].fillna(3).astype(int)
    
    # ==== STEP 4: Calculate Total RFM Score ====
    df['rfm_score'] = df['r_score'] + df['f_score'] + df['m_score']
    
    # ==== STEP 5: Segment Mapping ====
    def map_segment(score):
        if 12 <= score <= 15:
            return CustomerCategory.BOTH.value  # VIP/Champion
        elif 8 <= score <= 11:
            return CustomerCategory.FREQUENT_CUSTOMER.value  # Frequent/Loyal
        elif 5 <= score <= 7:
            return CustomerCategory.BULK_BUYER.value  # Bulk/Potential
        else:  # 3-4
            return CustomerCategory.REGULAR.value  # Regular/At-Risk
    
    df['category'] = df['rfm_score'].apply(map_segment)
    df['segment'] = df['category']
    
    # Calculate classification counts
    classifications = df['category'].value_counts().to_dict()
    
    # Calculate metrics for transparency
    rfm_info = {
        'method': 'Hybrid RFM (Log + Z-Score + Quintile)',
        'recency_mean': float(df['recency'].mean()),
        'frequency_mean': float(df['frequency'].mean()),
        'monetary_mean': float(df['monetary'].mean()),
        'rfm_score_distribution': {
            '12-15 (VIP)': int((df['rfm_score'] >= 12).sum()),
            '8-11 (Loyal)': int(((df['rfm_score'] >= 8) & (df['rfm_score'] < 12)).sum()),
            '5-7 (Potential)': int(((df['rfm_score'] >= 5) & (df['rfm_score'] < 8)).sum()),
            '3-4 (At-Risk)': int((df['rfm_score'] < 5).sum())
        }
    }
    
    return df, classifications, rfm_info


def classify_customers_dynamic(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
    percentile: int = 70
) -> tuple[pd.DataFrame, Dict[str, int], Dict[str, Any]]:
    """
    DEPRECATED: Use classify_customers_rfm instead.
    Kept for backward compatibility.
    """
    return classify_customers_rfm(df, column_mapping)


def classify_customers(df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, int]]:
    """
    DEPRECATED: Backward-compatible classification function.
    Use classify_customers_rfm for new implementations.
    """
    df_result, classifications, _ = classify_customers_rfm(df, None)
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
