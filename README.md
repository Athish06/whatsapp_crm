# WhatsApp CRM

A WhatsApp CRM application for managing customer communications and batch messaging campaigns.

## Tech Stack

- **Backend**: FastAPI + MongoDB (Motor async driver)
- **Frontend**: React + ShadCN UI

## Project Structure

```
whatsapp/
├── backend/
│   ├── config/         # Database and app configuration
│   ├── middleware/     # Authentication middleware
│   ├── routes/         # API endpoints
│   ├── schemas/        # Pydantic models
│   ├── services/       # Business logic
│   ├── utils/          # Helper utilities
│   ├── server.py       # Main app entry
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/ # UI components
│       ├── context/    # React context (Auth)
│       ├── pages/      # Page components
│       └── lib/        # API utilities
```

## Setup

### Backend

1. Install dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Configure MongoDB in `.env`:
   ```
   MONGO_URL="mongodb+srv://<username>:<password>@<cluster>.mongodb.net/"
   DB_NAME="whatsapp_crm"
   JWT_SECRET_KEY="your-secret-key"
   CORS_ORIGINS="http://localhost:3000"
   ```

3. Start the server:
   ```bash
   uvicorn server:app --reload --port 8000
   ```

### Frontend

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Configure backend URL in `.env`:
   ```
   REACT_APP_BACKEND_URL=http://localhost:8000
   ```

3. Start the dev server:
   ```bash
   npm start
   ```

## API Endpoints

- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - User login
- `POST /api/customers/upload` - Upload customers CSV
- `GET /api/customers/list` - List customers
- `POST /api/templates/create` - Create message template
- `GET /api/templates/list` - List templates
- `POST /api/batches/create` - Create batch campaign
- `GET /api/batches/list` - List batches
- `GET /api/dashboard/stats` - Dashboard statistics
