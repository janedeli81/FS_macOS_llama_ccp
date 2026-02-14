# Forensic Summarizer Backend API

FastAPI backend for authentication, payments, and document usage tracking.

## Features

- 🔐 JWT-based authentication
- 💳 Stripe payment integration (pay-per-document packages)
- 🎁 7-day trial period for new users
- 📊 Document usage tracking
- 💾 SQLite database (development)

## Quick Start (Windows)

### 1. Install Dependencies

```bash
cd backend_api
pip install -r requirements.txt
```

### 2. Configure Environment

Edit `.env` file and add your Stripe test keys:

```env
STRIPE_SECRET_KEY=sk_test_your_key_here
STRIPE_PUBLISHABLE_KEY=pk_test_your_key_here
```

Get your test keys from: https://dashboard.stripe.com/test/apikeys

### 3. Run Server

```bash
python -m uvicorn main:app --reload
```

Server will start at: http://localhost:8000

### 4. Test API

Open in browser: http://localhost:8000/docs

You'll see interactive Swagger documentation where you can test all endpoints.

## API Endpoints

### Authentication
- `POST /auth/register` - Register new user (auto 7-day trial)
- `POST /auth/login` - Login and get JWT token

### User Management
- `GET /users/me` - Get user profile
- `GET /users/status` - Quick status check (trial, balance)

### Payments
- `POST /payments/create-intent` - Create Stripe payment intent
- `POST /payments/confirm` - Confirm payment and add documents

### Document Processing
- `POST /documents/process` - Deduct document from balance

### Transactions
- `GET /transactions` - Get payment history

## Package Pricing

Defined in `.env` file (amounts in cents):

- **Package 10**: $9.99 (10 documents)
- **Package 50**: $39.99 (50 documents)
- **Package 100**: $69.99 (100 documents)

## Testing Payment Flow

### 1. Register User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 2. Check User Status

```bash
curl -X GET http://localhost:8000/users/status \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

Response:
```json
{
  "can_process": true,
  "is_trial": true,
  "trial_ends_at": "2026-02-21T12:00:00",
  "documents_remaining": 0,
  "subscription_active": false
}
```

### 3. Create Payment Intent

```bash
curl -X POST http://localhost:8000/payments/create-intent \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"package_type":"package_10"}'
```

Response:
```json
{
  "client_secret": "pi_xxx_secret_xxx",
  "amount": 999,
  "currency": "usd"
}
```

### 4. Test Payment (Stripe Test Cards)

Use these test card numbers in Stripe Elements:

- **Success**: 4242 4242 4242 4242
- **Requires authentication**: 4000 0025 0000 3155
- **Declined**: 4000 0000 0000 9995

Any future expiry date and any 3-digit CVC.

## Database Schema

### Users Table
- Trial period tracking
- Document balance (pay-per-document)
- Subscription status (optional)

### Transactions Table
- Stripe payment tracking
- Package purchases
- Payment status

### Usage Logs Table
- Document processing history
- Analytics data

## Integration with Desktop App

Your PyQt5 app should:

1. **On Login**: Call `/auth/login`, store JWT token
2. **Before Processing**: Call `/documents/process` with token
3. **Check Status**: Periodically call `/users/status`
4. **Purchase Packages**: Use `/payments/create-intent` + Stripe Elements

## Security Notes

⚠️ **For Development Only:**
- `.env` file contains secrets (add to `.gitignore`)
- SECRET_KEY should be random in production
- Use HTTPS in production
- Enable email verification
- Add rate limiting

## Stripe Webhook Testing

Install Stripe CLI:
```bash
# Download from: https://stripe.com/docs/stripe-cli
stripe login
stripe listen --forward-to localhost:8000/webhook/stripe
```

This forwards Stripe events to your local server.

## Production Deployment

1. Use PostgreSQL instead of SQLite
2. Set strong SECRET_KEY (use: `openssl rand -hex 32`)
3. Enable HTTPS
4. Configure real Stripe keys
5. Add email verification
6. Remove debug endpoints
7. Deploy to Railway/Fly.io/Heroku

## Troubleshooting

**Database locked error:**
```bash
# Delete and recreate database
rm forensic_app.db
python main.py
```

**Stripe key error:**
- Check `.env` file has correct test keys
- Keys should start with `sk_test_` and `pk_test_`

**CORS error from desktop app:**
- Add your app's origin to `CORS_ORIGINS` in `.env`

## Support

For issues, check:
- FastAPI docs: http://localhost:8000/docs
- Stripe dashboard: https://dashboard.stripe.com/test/payments
- Database: Use SQLite browser to inspect `forensic_app.db`
