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

# Database setup
def get_db():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

# Create users table if it doesn't exist
with get_db() as conn:
    conn.execute('''
    CREATE TABLE IF NOT EXISTS users
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
     email TEXT UNIQUE NOT NULL,
     name TEXT,
     subscription_status TEXT)
    ''')

# User model
class User(BaseModel):
    email: str
    name: str
    subscription_status: str = None

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
        logger.info(f"Token keys: {list(token.keys())}")
        
        if 'id_token' not in token:
            logger.error("id_token not found in token")
            raise HTTPException(status_code=400, detail="ID token missing")
        
        user = await oauth.google.parse_id_token(request, token)
        request.session['user'] = dict(user)
        
        # Check if user exists in the database, if not, add them
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE email = ?", (user['email'],))
            existing_user = c.fetchone()
            if not existing_user:
                c.execute("INSERT INTO users (email, name) VALUES (?, ?)",
                          (user['email'], user.get('name', 'Unknown')))
        
        # Redirect the user to the payment page
        return RedirectResponse(url='/payment')
    except Exception as e:
        logger.error(f"Error during authentication: {str(e)}")
        raise HTTPException(status_code=400, detail="Authentication failed")

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

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    data = await request.json()
    price_id = data.get('priceId')
    
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
            success_url=request.url_for('app'),
            cancel_url=request.url_for('payment'),
        )
        return {"id": checkout_session.id}
    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")

@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url='/signin')
    
    # Check subscription status
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT subscription_status FROM users WHERE email = ?", (user.email,))
        subscription = c.fetchone()
    
    if not subscription or subscription[0] not in ['active', 'trialing']:
        logger.warning(f'User {user.email} attempted to access app without active subscription')
        return RedirectResponse(url='/payment')
    
    return templates.TemplateResponse("app.html", {"request": request, "user": user})

@app.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    return user

@app.post("/profile")
async def update_profile(profile: User, current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET name = ? WHERE email = ?",
                  (profile.name, current_user.email))
    
    return {"message": "Profile updated successfully"}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
