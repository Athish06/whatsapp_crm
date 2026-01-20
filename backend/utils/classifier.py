import pandas as pd
from typing import Dict, List, Any
from schemas import CustomerCategory
import io
import re

try:
    import PyPDF2
    import pdfplumber
except ImportError:
    PyPDF2 = None
    pdfplumber = None

def classify_customers(df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, int]]:
    """
    Classify customers based on purchase patterns.
    
    Logic:
    - Bulk Buyer: High total_quantity (>= 50) or high order_value (>= 5000)
    - Frequent Customer: High purchase_count (>= 10)
    - Both: Meets both bulk and frequent criteria
    - Regular: Everyone else
    """
    # Calculate metrics if not present
    if 'total_quantity' not in df.columns:
        df['total_quantity'] = df.get('quantity', 0)
    
    if 'purchase_count' not in df.columns:
        df['purchase_count'] = df.get('orders', 1)
    
    if 'order_value' not in df.columns:
        df['order_value'] = df.get('amount', 0)
    
    # Classification logic
    def classify_row(row):
        is_bulk = (row.get('total_quantity', 0) >= 50) or (row.get('order_value', 0) >= 5000)
        is_frequent = row.get('purchase_count', 0) >= 10
        
        if is_bulk and is_frequent:
            return CustomerCategory.BOTH.value
        elif is_bulk:
            return CustomerCategory.BULK_BUYER.value
        elif is_frequent:
            return CustomerCategory.FREQUENT_CUSTOMER.value
        else:
            return CustomerCategory.REGULAR.value
    
    df['category'] = df.apply(classify_row, axis=1)
    
    # Calculate classification counts
    classifications = df['category'].value_counts().to_dict()
    
    return df, classifications

def parse_csv_file(file_content: bytes, filename: str) -> pd.DataFrame:
    """
    Parse uploaded CSV/Excel/PDF file and extract customer data.
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
    
    # Standardize column names
    df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')
    
    # Map common column variations to standard names
    column_mapping = {
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
    
    df.rename(columns=column_mapping, inplace=True)
    
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
    
    if 'total_quantity' not in df.columns:
        df['total_quantity'] = 0
    
    if 'purchase_count' not in df.columns:
        df['purchase_count'] = 1
    
    if 'order_value' not in df.columns:
        df['order_value'] = 0
    
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
