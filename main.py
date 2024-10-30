import os
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
import stripe
import sqlite3
from pydantic import BaseModel
import logging
import httpx
from typing import Optional

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Initialize Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
stripe_webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

# Database setup
def get_db():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

# Create users table if it doesn't exist
with get_db() as conn:
    conn.execute('''
    CREATE TABLE IF NOT EXISTS users
    (sub TEXT PRIMARY KEY,
     email TEXT UNIQUE NOT NULL,
     name TEXT,
     picture TEXT,
     subscription_status TEXT,
     club TEXT DEFAULT NULL,
     coach TEXT DEFAULT NULL,
     discipline TEXT DEFAULT NULL,
     personal_best INTEGER DEFAULT NULL)
    ''')

# User model
class User(BaseModel):
    sub: str
    email: str
    name: str
    picture: str
    subscription_status: Optional[str] = None
    club: Optional[str] = None
    coach: Optional[str] = None
    discipline: Optional[str] = None
    personal_best: Optional[int] = None

class CheckoutSessionRequest(BaseModel):
    priceId: str

class ProfileUpdate(BaseModel):
    name: str
    club: str
    coach: str
    discipline: str
    personal_best: int

# Helper function to get current user
async def get_current_user(request: Request):
    user = request.session.get('user')
    if user:
        return User(**user)
    return None

# Routes
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, user: User = Depends(get_current_user)):
    if user:
        return RedirectResponse(url='/app')
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/signin", response_class=HTMLResponse)
async def signin(request: Request):
    return templates.TemplateResponse("signin.html", {"request": request})

@app.get('/login')
async def login(request: Request):
    redirect_uri = request.url_for('auth')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get('/auth')
async def auth(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        logger.info(f"Token received: {token}")
    except Exception as e:
        logger.error(f"Error during OAuth access token retrieval: {str(e)}")
        raise HTTPException(status_code=400, detail="Failed to retrieve access token")
    
    access_token = token.get('access_token')
    if not access_token:
        logger.error("access_token missing in token")
        raise HTTPException(status_code=400, detail="Access token missing")
    
    # Fetch user information from Google
    async with httpx.AsyncClient() as client:
        try:
            user_info_response = await client.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                headers={'Authorization': f'Bearer {access_token}'}
            )
            user_info_response.raise_for_status()
            user_info = user_info_response.json()
            logger.info(f"User info received: {user_info}")
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch user info: {str(e)}")
            raise HTTPException(status_code=400, detail="Failed to fetch user info")
    
    request.session['user'] = user_info
    
    # Check if user exists and their subscription status
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (user_info.get('email'),))
        existing_user = c.fetchone()
        if not existing_user:
            c.execute("INSERT INTO users (sub, email, name) VALUES (?, ?, ?)",
            (user_info.get('sub'), user_info.get('email'), user_info.get('name')))
            conn.commit()
        else:
            c.execute("SELECT subscription_status FROM users WHERE email = ?", (user_info.get('email'),))
            user_sub = c.fetchone()
            if user_sub and user_sub[0] == 'active':
                return RedirectResponse(url='/app')
    
    # If no active subscription, redirect to payment
    return RedirectResponse(url='/payment')

@app.get('/logout')
async def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url='/')

@app.get("/payment", response_class=HTMLResponse)
async def payment(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url='/signin')
    return templates.TemplateResponse("payment.html", {
        "request": request,
        "STRIPE_MONTHLY_PRICE_ID": os.getenv('STRIPE_MONTHLY_PRICE_ID'),
        "STRIPE_YEARLY_PRICE_ID": os.getenv('STRIPE_YEARLY_PRICE_ID')
    })

@app.get("/subscription", response_class=HTMLResponse)
async def subscription_details(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url='/signin')
    
    try:
        # First get the customer ID using the email
        customers = stripe.Customer.list(
            email=user.email,
            limit=1
        )
        
        if not customers.data:
            logger.warning(f'No customer found for user {user.email}')
            return RedirectResponse(url='/payment')
            
        customer = customers.data[0]
        
        # Then get subscriptions for this customer
        subscriptions = stripe.Subscription.list(
            customer=customer.id,
            limit=1,
            status='active'
        )
        
        if not subscriptions.data:
            logger.warning(f"No active subscription found for user {user.email}")
            return RedirectResponse(url='/payment')
            
        subscription = subscriptions.data[0]
        
        subscription_data = {
            'plan_name': subscription.plan.nickname,
            'status': subscription.status,
            'current_period_end': subscription.current_period_end,
            'amount': subscription.plan.amount / 100,  # Convert cents to dollars
            'currency': subscription.plan.currency,
            'interval': subscription.plan.interval
        }
        
        return templates.TemplateResponse(
            "subscription.html", 
            {"request": request, "user": user, "subscription": subscription_data}
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error fetching subscription: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching subscription details")

@app.post("/create-checkout-session")
async def create_checkout_session(
    checkout_request: CheckoutSessionRequest,
    user: User = Depends(get_current_user)
):
    if not user:
        logger.warning("Unauthenticated user attempted to create a checkout session.")
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    price_id = checkout_request.priceId
    
    if not price_id:
        logger.error("Price ID not provided in the request.")
        raise HTTPException(status_code=400, detail="Price ID is required.")
    
    # Ensure BASE_URL is set
    base_url = os.getenv('BASE_URL')
    if not base_url:
        logger.error("BASE_URL environment variable not set.")
        raise HTTPException(status_code=500, detail="Server configuration error.")
    
    success_url = f"{base_url}/app?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base_url}/payment"
    
    try:
        checkout_session = stripe.checkout.Session.create(
            client_reference_id=user.email,
            customer_email=user.email,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return {"id": checkout_session.id}
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Stripe error creating checkout session")
    except Exception as e:
        logger.error(f"Unexpected error creating checkout session: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create checkout session")

@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url='/signin')
    
    try:
        # First get the customer ID using the email
        customers = stripe.Customer.list(
            email=user.email,
            limit=1
        )
        
        if not customers.data:
            logger.warning(f'No customer found for user {user.email}')
            return RedirectResponse(url='/payment')
            
        customer = customers.data[0]
        
        # Then get subscriptions for this customer
        subscriptions = stripe.Subscription.list(
            customer=customer.id,
            limit=1,
            status='active'
        )
        
        if not subscriptions.data:
            logger.warning(f'User {user.email} has no active subscription')
            return RedirectResponse(url='/payment')
        
        return templates.TemplateResponse("app.html", {"request": request, "user": user})
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error checking subscription: {str(e)}")
        raise HTTPException(status_code=500, detail="Error checking subscription status")

@app.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT name, club, coach, discipline, personal_best 
            FROM users 
            WHERE email = ?
        """, (user.email,))
        result = c.fetchone()
        
    if result:
        return {
            "name": result[0],
            "club": result[1],
            "coach": result[2],
            "discipline": result[3],
            "personal_best": result[4]
        }
    return {}

@app.post("/profile")
async def update_profile(profile: ProfileUpdate, user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE users 
            SET name = ?, club = ?, coach = ?, discipline = ?, personal_best = ?
            WHERE sub = ?
        """, (profile.name, profile.club, profile.coach, profile.discipline, profile.personal_best, user.sub))
        
    return {"status": "success"}

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session.get('customer_details', {}).get('email')
        
        if not customer_email:
            logger.error("Customer email not found in the session data")
            return {"status": "error", "message": "Customer email not found"}

        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("UPDATE users SET subscription_status = 'active' WHERE email = ?", (customer_email,))
                if c.rowcount == 0:
                    logger.warning(f"No user found with email: {customer_email}")
                conn.commit()
            logger.info(f"Subscription activated for user: {customer_email}")
        except Exception as e:
            logger.error(f"Error updating subscription status: {str(e)}")
            return {"status": "error", "message": "Database update failed"}

    return {"status": "success"}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
