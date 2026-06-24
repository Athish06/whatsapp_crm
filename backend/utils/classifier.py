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
    Hybrid RFM+B Intelligence: Enterprise-Grade Segmentation with Bulkiness Factor.
    
    Phase 1: Feature Engineering (Raw Metrics)
        - Recency (R_raw): Days since last purchase
        - Frequency (F_raw): Total purchase count
        - Monetary (M_raw): Total spending
        - Bulkiness (B_raw): Avg items per transaction (Basket Size)
    
    Phase 2: Quintile Scoring (1-5 scale)
        - R: Lower is better (recent = 5)
        - F, M: Higher is better (top 20% = 5)
        - Total Score = R + F + M (range: 3-15)
    
    Phase 3: 5-Tier Waterfall Decision Tree
        1. VIP: Total >= 12
        2. At-Risk: R=1 AND Total>4 (urgent churn prevention)
        3. Potential (Bulk): 5-11 AND B > Store Average
        4. Loyal (Frequent): 5-11 AND F >= M
        5. Boring: Total <= 4 OR no other rules met
    
    Args:
        df: DataFrame with customer data
        column_mapping: Map of standard names to actual column names
        today: Reference date for recency calculation (defaults to today)
    
    Returns:
        Tuple of (classified_df, segment_counts, rfm_info)
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
    if 'total_quantity' not in df.columns:
        df['total_quantity'] = 0
    if 'last_transaction_date' not in df.columns:
        df['last_transaction_date'] = pd.Timestamp.now()
    
    # Convert to numeric types
    df['purchase_count'] = pd.to_numeric(df['purchase_count'], errors='coerce').fillna(1).replace(0, 1)
    df['order_value'] = pd.to_numeric(df['order_value'], errors='coerce').fillna(0)
    df['total_quantity'] = pd.to_numeric(df['total_quantity'], errors='coerce').fillna(0)
    
    # Parse last transaction date
    if today is None:
        today = pd.Timestamp.now()
    
    df['last_transaction_date'] = pd.to_datetime(df['last_transaction_date'], errors='coerce')
    df['last_transaction_date'] = df['last_transaction_date'].fillna(today)
    
    # ==== PHASE 1: FEATURE ENGINEERING (Raw Metrics) ====
    # Step 1: Raw Recency (days since last purchase)
    df['recency_raw'] = (today - df['last_transaction_date']).dt.days
    df['recency_raw'] = df['recency_raw'].clip(lower=0)  # Ensure non-negative
    df['recency'] = df['recency_raw']  # alias kept for downstream compatibility
    df['frequency'] = pd.to_numeric(df['purchase_count'], errors='coerce').fillna(1)
    df['monetary'] = pd.to_numeric(df['order_value'], errors='coerce').fillna(0)
    df['monetary_log'] = np.log1p(df['monetary'])  # log(1+x) — dampens whale distortion
    df['bulkiness'] = (df['total_quantity'] / df['purchase_count']).fillna(0)  # Avg items/txn
    
    # Calculate store average bulkiness for waterfall threshold (unchanged)
    store_avg_bulkiness = df['bulkiness'].mean()
    
    # ==== PHASE 2: QUINTILE SCORING (1-5) ====
    # -----------------------------------------------------------------
    # RECENCY SCORE — Rank-based Quintile Method
    #   Step 2: Rank raw recency (lowest days = most recent = lowest rank)
    #   Step 3: qcut on ranks with reversed labels so:
    #           Top 20% most recent (lowest rank) → Score 5
    #           Bottom 20% oldest  (highest rank) → Score 1
    # This handles ties and small datasets far better than direct qcut.
    # -----------------------------------------------------------------
    df['recency_rank'] = df['recency_raw'].rank(method='average')
    try:
        df['r_score'] = pd.qcut(
            df['recency_rank'],
            q=5,
            labels=[5, 4, 3, 2, 1],   # reversed: low rank (recent) → 5
            duplicates='drop'
        ).astype(int)
    except (ValueError, TypeError):
        # Fallback for very small / uniform datasets
        try:
            df['r_score'] = pd.cut(
                df['recency_rank'],
                bins=5,
                labels=[5, 4, 3, 2, 1],
                include_lowest=True
            ).astype(int)
        except Exception:
            df['r_score'] = 3  # default mid-range score
    
    # -----------------------------------------------------------------
    # FREQUENCY SCORE — Rank-based Quintile Method
    #   Higher purchase_count → higher rank → Score 5
    # -----------------------------------------------------------------
    df['f_rank'] = df['frequency'].rank(method='average')
    try:
        df['f_score'] = pd.qcut(
            df['f_rank'],
            q=5,
            labels=[1, 2, 3, 4, 5],   # high rank (frequent) → 5
            duplicates='drop'
        ).astype(int)
    except (ValueError, TypeError):
        try:
            df['f_score'] = pd.cut(
                df['f_rank'],
                bins=5,
                labels=[1, 2, 3, 4, 5],
                include_lowest=True
            ).astype(int)
        except Exception:
            df['f_score'] = 3

    # -----------------------------------------------------------------
    # MONETARY SCORE — Rank-based Quintile Method (log-transformed)
    #   log1p dampens whale distortion; high spender → Score 5
    # -----------------------------------------------------------------
    df['m_rank'] = df['monetary_log'].rank(method='average')
    try:
        df['m_score'] = pd.qcut(
            df['m_rank'],
            q=5,
            labels=[1, 2, 3, 4, 5],   # high rank (big spender) → 5
            duplicates='drop'
        ).astype(int)
    except (ValueError, TypeError):
        try:
            df['m_score'] = pd.cut(
                df['m_rank'],
                bins=5,
                labels=[1, 2, 3, 4, 5],
                include_lowest=True
            ).astype(int)
        except Exception:
            df['m_score'] = 3

    # -----------------------------------------------------------------
    # BULKINESS SCORE — Rank-based Quintile Method
    #   Higher avg basket size → higher rank → Score 5
    # -----------------------------------------------------------------
    df['b_rank'] = df['bulkiness'].rank(method='average')
    try:
        df['b_score'] = pd.qcut(
            df['b_rank'],
            q=5,
            labels=[1, 2, 3, 4, 5],   # high rank (bulk buyer) → 5
            duplicates='drop'
        ).astype(int)
    except (ValueError, TypeError):
        try:
            df['b_score'] = pd.cut(
                df['b_rank'],
                bins=5,
                labels=[1, 2, 3, 4, 5],
                include_lowest=True
            ).astype(int)
        except Exception:
            df['b_score'] = 3

    # Force all scores to int (guards against NaN edge-cases)
    df['r_score'] = pd.to_numeric(df['r_score'], errors='coerce').fillna(3).astype(int)
    df['f_score'] = pd.to_numeric(df['f_score'], errors='coerce').fillna(3).astype(int)
    df['m_score'] = pd.to_numeric(df['m_score'], errors='coerce').fillna(3).astype(int)
    df['b_score'] = pd.to_numeric(df['b_score'], errors='coerce').fillna(3).astype(int)
    
    # Calculate Total RFM Score
    df['rfm_score'] = df['r_score'] + df['f_score'] + df['m_score']
    df['rfm_score'] = pd.to_numeric(df['rfm_score'], errors='coerce').fillna(9).astype(int)
    
    # ==== PHASE 3: 5-TIER WATERFALL DECISION TREE ====
    def apply_waterfall_segmentation(row, previous_segment=None):
        total_score = row['rfm_score']
        r_score = row['r_score']
        f_score = row['f_score']
        m_score = row['m_score']
        b_score = row.get('b_score', 3)
        purchase_count = row.get('purchase_count', 0)
        recency_days = row.get('recency_raw', 999)  # aliased to recency_raw earlier
        
        # ── Rule 0: NEW CUSTOMER (pre-waterfall escape) ──
        if purchase_count <= 2 and recency_days <= 30:
            return CustomerCategory.NEW_CUSTOMER.value
            
        # ── Rule 1: VIP (Champions) ──
        # Total >= 12, with frequency override for daily shoppers
        if total_score >= 12 and (m_score >= 4 or f_score == 5):
            return CustomerCategory.VIP.value
        
        # ── Rule 2: AT-RISK (Churn Prevention) ──
        # Classic trigger: low recency but was historically valuable
        if r_score <= 2 and (f_score + m_score) >= 5:
            return CustomerCategory.AT_RISK.value
        # Churn velocity: was VIP/Loyal last period, R is dropping
        if previous_segment in (CustomerCategory.VIP.value, CustomerCategory.LOYAL_FREQUENT.value) and r_score <= 3:
            return CustomerCategory.AT_RISK.value
        
        # ── Rule 3: POTENTIAL BULK (Pantry Stockers) ──
        if 5 <= total_score <= 11 and b_score >= 4:
            return CustomerCategory.POTENTIAL_BULK.value
        
        # ── Rule 4: LOYAL FREQUENT (Daily Habit) ──
        if 5 <= total_score <= 11 and f_score >= 3 and f_score >= m_score:
            return CustomerCategory.LOYAL_FREQUENT.value
        
        # ── Rule 5: BORING / OCCASIONAL (Baseline) ──
        return CustomerCategory.BORING.value
    
    df['category'] = df.apply(apply_waterfall_segmentation, axis=1)
    df['segment'] = df['category']
    
    # Calculate classification counts
    classifications = df['category'].value_counts().to_dict()
    
    # Calculate metrics for transparency
    rfm_info = {
        'method': 'Hybrid RFM+B Intelligence',
        'recency_mean': float(df['recency'].mean()),
        'frequency_mean': float(df['frequency'].mean()),
        'monetary_mean': float(df['monetary'].mean()),
        'bulkiness_mean': float(df['bulkiness'].mean()),
        'store_avg_bulkiness': float(store_avg_bulkiness),
        'segment_distribution': {
            'VIP': int((df['segment'] == CustomerCategory.VIP.value).sum()),
            'At-Risk': int((df['segment'] == CustomerCategory.AT_RISK.value).sum()),
            'Potential (Bulk)': int((df['segment'] == CustomerCategory.POTENTIAL_BULK.value).sum()),
            'Loyal (Frequent)': int((df['segment'] == CustomerCategory.LOYAL_FREQUENT.value).sum()),
            'Boring': int((df['segment'] == CustomerCategory.BORING.value).sum())
        },
        'rfm_score_distribution': {
            '12-15': int((df['rfm_score'] >= 12).sum()),
            '8-11': int(((df['rfm_score'] >= 8) & (df['rfm_score'] < 12)).sum()),
            '5-7': int(((df['rfm_score'] >= 5) & (df['rfm_score'] < 8)).sum()),
            '3-4': int((df['rfm_score'] < 5).sum())
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
