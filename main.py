import sqlite3, config
# import populate_stocks, populate_prices
from opening_range_breakout import place_opening_range_breakout_orders
from opening_range_breakdown import place_opening_range_breakdown_orders
from delete_user import delete_user
from make_admin import make_admin
import smtplib, ssl
import alpaca_trade_api as tradeapi
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from datetime import date, timedelta
from starlette.responses import RedirectResponse
from typing import Optional
import base64

app = FastAPI()

templates = Jinja2Templates(directory="templates")

@app.get("/")
def index(request: Request):

    username = config.USERNAME

    if username == "":
        return templates.TemplateResponse("welcome.html", {"request": request, "failure": "You need to be logged in for that."})

    stock_filter = request.query_params.get('filter', False)

    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    if stock_filter == 'new_closing_highs':
        cursor.execute("""
        select * from (
            select  symbol, name, stock_id, max(close), date
            from stock_price join stock on stock.id = stock_price.stock_id
            group by stock_id
            order by symbol
        ) where date = (select max(date) from stock_price)
        """)
    elif stock_filter == 'new_closing_lows':
        cursor.execute("""
        select * from (
            select  symbol, name, stock_id, min(close), date
            from stock_price join stock on stock.id = stock_price.stock_id
            group by stock_id
            order by symbol
        ) where date  = (select max(date) from stock_price)
        """)
    elif stock_filter == 'rsi_overbought':
        cursor.execute("""
            select  symbol, name, stock_id, date
            from stock_price join stock on stock.id = stock_price.stock_id
            where rsi_14 > 70
            and date = (select max(date) from stock_price)
            order by symbol
        """)
    elif stock_filter == 'rsi_oversold':
        cursor.execute("""
            select  symbol, name, stock_id, date
            from stock_price join stock on stock.id = stock_price.stock_id
            where rsi_14 < 30
            and date = (select max(date) from stock_price)
            order by symbol
        """)
    elif stock_filter == 'above_sma_20':
        cursor.execute("""
            select  symbol, name, stock_id, date
            from stock_price join stock on stock.id = stock_price.stock_id
            where close > sma_20
            and date = (select max(date) from stock_price)
            order by symbol
        """)
    elif stock_filter == 'below_sma_20':
        cursor.execute("""
            select  symbol, name, stock_id, date
            from stock_price join stock on stock.id = stock_price.stock_id
            where close < sma_20
            and date = (select max(date) from stock_price)
            order by symbol
        """)
    elif stock_filter == 'above_sma_50':
        cursor.execute("""
            select  symbol, name, stock_id, date
            from stock_price join stock on stock.id = stock_price.stock_id
            where close > sma_50
            and date = (select max(date) from stock_price)
            order by symbol
        """)
    elif stock_filter == 'below_sma_50':
        cursor.execute("""
            select  symbol, name, stock_id, date
            from stock_price join stock on stock.id = stock_price.stock_id
            where close < sma_50
            and date = (select max(date) from stock_price)
            order by symbol
        """)
    else:   
        cursor.execute("""
            SELECT id, symbol, name FROM stock order by symbol
        """)

    rows = cursor.fetchall()

    cursor.execute("""
        select symbol, rsi_14, sma_20, sma_50, close
        from stock join stock_price on stock_price.stock_id = stock.id
        where date = (select max(date) from stock_price)
    """)

    indicator_rows = cursor.fetchall()
    indicator_values = {}
    for row in indicator_rows:
        indicator_values[row['symbol']] = row

    return templates.TemplateResponse("index.html", {"request": request, "stocks": rows, "indicator_values": indicator_values, "username": config.USERNAME})

@app.get("/stock/{symbol}")
def stock_detail(request: Request, symbol):

    username = config.USERNAME

    if username == "":
        return templates.TemplateResponse("sign_in.html", {"request": request, "failure": "You need to be logged in for that."})

    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT * FROM strategy
    """)

    strategies = cursor.fetchall()

    cursor.execute("""
        SELECT id, symbol, name FROM stock where symbol = ?
    """, (symbol, ))

    row = cursor.fetchone()

    cursor.execute("""
        SELECT * FROM stock_price WHERE stock_id = ? order by date desc
    """, (row['id'],))

    prices = cursor.fetchall()

    return templates.TemplateResponse("stock_detail.html", {"request": request, "stock": row, "bars": prices, "strategies": strategies, "username": username})

@app.post("/apply_strategy")
def apply_strategy(strategy_id: int = Form(...), stock_id: int = Form(...)):

    username = config.USERNAME
    
    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id FROM users
        WHERE username = ?
    """, (username,))

    user_id = cursor.fetchone()
    current_id = user_id[0]

    cursor.execute("""
        INSERT INTO stock_strategy (stock_id, strategy_id, user_id) VALUES (?, ?, ?)    
    """, (stock_id, strategy_id, current_id))

    connection.commit()
    
    return RedirectResponse(url=f"/strategy/{strategy_id}", status_code=303)

@app.get("/strategies")
def strategies(request: Request):
    
    username = config.USERNAME

    if username == "":
        return templates.TemplateResponse("sign_in.html", {"request": request, "failure": "You need to be logged in for that."})

    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT * FROM strategy
    """)

    strategies = cursor.fetchall()

    return templates.TemplateResponse("strategies.html", {"request": request, "strategies": strategies, "username": username})

@app.get("/orders")
def orders(request: Request):

    username = config.USERNAME

    if username == "":
        return templates.TemplateResponse("sign_in.html", {"request": request, "failure": "You need to be logged in for that."})

    api = tradeapi.REST(config.API_KEY, config.SECRET_KEY, base_url=config.BASE_URL)
    orders = api.list_orders(status='all')

    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders, "username": username})

@app.get("/strategy/{strategy_id}")
def strategy(request: Request, strategy_id, info: Optional[str] = None):

    username = config.USERNAME

    if username == "":
        return templates.TemplateResponse("sign_in.html", {"request": request, "failure": "You need to be logged in for that."})

    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, name
        FROM strategy
        WHERE id = ?
    """, (strategy_id,))

    strategy = cursor.fetchone()

    cursor.execute("""
        SELECT id FROM users
        WHERE username = ?
    """, (username,))

    user_id = cursor.fetchone()
    current_id = user_id[0]

    cursor.execute("""
        SELECT symbol, name
        FROM stock JOIN stock_strategy on stock_strategy.stock_id = stock.id
        WHERE strategy_id = ?
        AND user_id = ?
    """, (strategy_id, current_id,))

    stocks = cursor.fetchall()

    return templates.TemplateResponse("strategy.html", {"request": request, "stocks": stocks, "strategy": strategy, "username": username, "info": info})


@app.get("/sign_in")
def sign_in(request: Request):
    return templates.TemplateResponse("sign_in.html", {"request": request})

@app.post("/sign_in")
def sign_in(request: Request):
    return templates.TemplateResponse("sign_in.html", {"request": request})

@app.get("/logout")
def sign_in(request: Request):
    config.USERNAME = "" 
    return templates.TemplateResponse("welcome.html", {"request": request})


@app.post("/user_entry")
def user_entry(request: Request, username: str = Form(...), password: str = Form(...)):
    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT count(*) 
        FROM users
        WHERE username = ?
    """, (username,))

    users = cursor.fetchone()

    if users [0] == 0:

        cursor.execute("""
            SELECT count(*) 
            FROM users
            WHERE email = ?
        """, (username,))

        users = cursor.fetchone()

        if users [0] == 0:
            return templates.TemplateResponse("sign_in.html", {"request": request, "failure": "We couldn't find a username/email like that"})
        else:
            using_email = True
            cursor.execute("""
                SELECT password 
                FROM users
                WHERE email = ?
            """, (username,))
    else: 
        using_email = False
        cursor.execute("""
            SELECT password 
            FROM users
            WHERE username = ?
        """, (username,))

    actual_password = cursor.fetchone()

    base64_string = str(actual_password[0])
    base64_bytes = base64_string.encode("ascii")

    actual_string_bytes = base64.b64decode(base64_bytes)
    actual_string = actual_string_bytes.decode("ascii")

    if str(actual_string) == str(password):
        if using_email:
            cursor.execute("""
                    SELECT username 
                    FROM users
                    WHERE email = ?
                """, (username,))
        else:
            cursor.execute("""
                    SELECT username 
                    FROM users
                    WHERE username = ?
                """, (username,))

        config.USERNAME = cursor.fetchone()[0]
        return RedirectResponse(url=f"/", status_code=303)

    return templates.TemplateResponse("sign_in.html", {"request": request, "failure": "Username and password do not match our records"})

@app.get("/register")
def register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/new_user")
def register(request: Request, username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT username, email
        FROM users
    """)

    users = cursor.fetchall()

    usernames = []
    for user in users:
        usernames.append(user[0])

    print(usernames)
    
    if username in usernames:
        return templates.TemplateResponse("register.html", {"request": request, "failure": "Username already exists"})

    emails = []
    for user in users:
        emails.append(user[1])

    if email in emails:
        return templates.TemplateResponse("register.html", {"request": request, "failure": "Email already in use"})
    
    password_bytes = password.encode("ascii")
    base64_bytes = base64.b64encode(password_bytes)
    base64_string = base64_bytes.decode("ascii")

    cursor.execute("""
        INSERT INTO users (username, email, password) VALUES (?, ?, ?)    
    """, (username, email, base64_string))

    connection.commit()

    return templates.TemplateResponse("sign_in.html", {"request": request, "new_user": "Account created. You can now log in."})

@app.get("/place_order/{strategy_id}")
def stock_detail(request: Request, strategy_id):
    if strategy_id == "1":
        place_opening_range_breakout_orders()
    elif strategy_id == "2": 
        place_opening_range_breakdown_orders()
    return RedirectResponse(url=f"/strategy/{strategy_id}?info=1", status_code=303)

@app.get("/admin")
def admin(request: Request):
    username = config.USERNAME

    if username == "":
        return templates.TemplateResponse("sign_in.html", {"request": request, "failure": "You need to be logged in for that."})
    
    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT admin FROM users
        WHERE username = ?
    """, (username,))

    is_admin = cursor.fetchone()

    if is_admin[0] == 1:
        connection = sqlite3.connect(config.DB_FILE)
        connection.row_factory = sqlite3.Row

        cursor = connection.cursor()

        cursor.execute("""
            SELECT id, username, admin
            FROM users
        """)

        users = cursor.fetchall()

        return templates.TemplateResponse("admin.html", {"request": request, "users": users, "username": username})

    else:
        

        context = ssl.create_default_context()

        with smtplib.SMTP_SSL("smtp.gmail.com", config.EMAIL_PORT, context=context) as server:
            server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
            email_message = f'Subject: Unathorized user: {config.USERNAME} trying to enter Admin area\n\n'
            email_message += f'\n\nThe user {config.USERNAME} has tried to acces the admin zone. Should this not be a known attempt, consider deleting said account.\n\n Sincerely, \n The team at Get Rich or Try Again'
            server.sendmail(config.EMAIL_ADDRESS, config.EMAIL_ADDRESS, email_message)

        config.USERNAME = "" 

        return templates.TemplateResponse("sign_in.html", {"request": request, "failure": "An admin account is required for that operation. You've been logged out for safety."})

@app.get("/delete_user/{user_id}")
def delete(request: Request, user_id):
    delete_user(user_id)
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/make_admin/{user_id}")
def delete(request: Request, user_id):
    make_admin(user_id)
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/profile/{username}")
def strategy(request: Request, username):

    username = config.USERNAME

    if username == "":
        return templates.TemplateResponse("sign_in.html", {"request": request, "failure": "You need to be logged in for that."})
    
    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
            SELECT email 
            FROM users
            WHERE username = ?
        """, (username,))

    email = cursor.fetchone()[0]

    return templates.TemplateResponse("user_profile.html", {"request": request, "username": username, "email": email})

@app.post("/user_change")
def user_entry(request: Request, username: str = Form(...), email: Optional[str] = Form(...), current_password: str = Form(...), new_password: Optional[str] = Form(None)):

    
    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
            SELECT password 
            FROM users
            WHERE username = ?
        """, (config.USERNAME,))

    actual_password = cursor.fetchone()

    base64_string = str(actual_password[0])
    base64_bytes = base64_string.encode("ascii")

    actual_string_bytes = base64.b64decode(base64_bytes)
    actual_string = actual_string_bytes.decode("ascii")

    cursor.execute("""
            SELECT email 
            FROM users
            WHERE username = ?
        """, (config.USERNAME,))

    current_email = cursor.fetchone()[0]

    if current_password == actual_string:

        if current_email != email:

            cursor.execute("""
                SELECT count(*) 
                FROM users
                WHERE email = ?
            """, (email,))

            users = cursor.fetchone()

            if users [0] != 0:
                return templates.TemplateResponse("user_profile.html", {"request": request, "username": username, "email": current_email, "failure": "Email already in use"})
            else:
                cursor.execute("""
                    UPDATE users
                    SET email = ?
                    WHERE username = ?
                """, (email, config.USERNAME))

        if username != config.USERNAME:

            cursor.execute("""
                SELECT count(*) 
                FROM users
                WHERE username = ?
            """, (username,))

            users = cursor.fetchone()

            if users[0] != 0:
                return templates.TemplateResponse("user_profile.html", {"request": request, "username": config.USERNAME, "email": current_email, "failure": "Username not available"})
            else:
                cursor.execute("""
                    UPDATE users
                    SET username = ?
                    WHERE username = ?
                """, (username, config.USERNAME))

                config.USERNAME = username

        if new_password is not None:

            password_bytes = new_password.encode("ascii")
            base64_bytes = base64.b64encode(password_bytes)
            base64_string = base64_bytes.decode("ascii")

            cursor.execute("""
                        UPDATE users
                        SET password = ?
                        WHERE username = ?
                    """, (base64_string, config.USERNAME))

    else:
        if email:
            pass
        else:
            email = current_email
        return templates.TemplateResponse("user_profile.html", {"request": request, "username": username, "email": email, "failure": "Wrong Password"})
        
    connection.commit()

    config.USERNAME = "" 

    return templates.TemplateResponse("sign_in.html", {"request": request, "success": "Changes made accordingly. You've been logged out. Please log in again with your updated credentials."})




