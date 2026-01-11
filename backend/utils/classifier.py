import pandas as pd
from typing import Dict, List, Any
from schemas import CustomerCategory

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
    Parse uploaded CSV/Excel file.
    """
    if filename.endswith('.csv'):
        df = pd.read_csv(pd.io.common.BytesIO(file_content))
    elif filename.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(pd.io.common.BytesIO(file_content))
    else:
        raise ValueError("Unsupported file format. Please upload CSV or Excel file.")
    
    # Standardize column names
    df.columns = df.columns.str.lower().str.strip()
    
    # Validate required columns
    required_cols = ['name', 'phone']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"File must contain columns: {', '.join(required_cols)}")
    
    return df

def prepare_message(template: str, customer_data: Dict[str, Any]) -> str:
    """
    Replace placeholders in message template with customer data.
    """
    message = template
    for key, value in customer_data.items():
        placeholder = f"{{{{{key}}}}}"
        message = message.replace(placeholder, str(value))
    return message
