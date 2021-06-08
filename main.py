import sqlite3, config
import alpaca_trade_api as tradeapi
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from datetime import date, timedelta

from starlette.responses import RedirectResponse

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
def index(request: Request):
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

    return templates.TemplateResponse("index.html", {"request": request, "stocks": rows, "indicator_values": indicator_values})

@app.get("/stock/{symbol}")
def stock_detail(request: Request, symbol):
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

    return templates.TemplateResponse("stock_detail.html", {"request": request, "stock": row, "bars": prices, "strategies": strategies})

@app.post("/apply_strategy")
def apply_strategy(strategy_id: int = Form(...), stock_id: int = Form(...)):
    connection = sqlite3.connect(config.DB_FILE)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO stock_strategy (stock_id, strategy_id) VALUES (?, ?)    
    """, (stock_id, strategy_id))

    connection.commit()
    
    return RedirectResponse(url=f"/strategy/{strategy_id}", status_code=303)

@app.get("/strategies")
def strategies(request: Request):
    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT * FROM strategy
    """)

    strategies = cursor.fetchall()

    return templates.TemplateResponse("strategies.html", {"request": request, "strategies": strategies})

@app.get("/orders")
def orders(request: Request):

    api = tradeapi.REST(config.API_KEY, config.SECRET_KEY, base_url=config.BASE_URL)
    orders = api.list_orders(status='all')

    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders})

@app.get("/strategy/{strategy_id}")
def strategy(request: Request, strategy_id):
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
        SELECT symbol, name
        FROM stock JOIN stock_strategy on stock_strategy.stock_id = stock.id
        WHERE strategy_id = ?
    """, (strategy_id,))

    stocks = cursor.fetchall()

    return templates.TemplateResponse("strategy.html", {"request": request, "stocks": stocks, "strategy": strategy})
