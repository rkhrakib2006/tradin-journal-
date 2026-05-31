import os
import secrets
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import pandas as pd
from bs4 import BeautifulSoup

# === 1. DATABASE CONFIG ===
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:password@localhost/trading_journal"
# Change 'postgres:password' to your local DB credentials (e.g., user:pass)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    hashed_password = Column(String)

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ticket_number = Column(Integer)
    symbol = Column(String)
    entry_time = Column(DateTime)
    exit_time = Column(DateTime)
    trade_type = Column(String)
    lot_size = Column(Float)
    profit_loss = Column(Numeric(10, 2))
    commission = Column(Numeric(10, 2), default=0)
    swap = Column(Numeric(10, 2), default=0)
    notes = Column(String, nullable=True)
    attachments = relationship("TradeAttachment", back_populates="trade")

class TradeAttachment(Base):
    __tablename__ = "trade_attachments"
    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(Integer, ForeignKey("trades.id"))
    file_name = Column(String)
    file_path = Column(String)
    trade = relationship("Trade", back_populates="attachments")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# === 2. MT5 PARSER ===
def parse_mt5_file(file_content, filename):
    trades = []
    try:
        if filename.endswith('.csv'):
            try:
                df = pd.read_csv(file_content, sep=';')
            except:
                df = pd.read_csv(file_content)
        else:
            soup = BeautifulSoup(file_content, 'html.parser')
            tables = soup.find_all('table')
            if not tables: return []
            df = pd.read_html(str(tables[0]))[0]
        
        cols = df.columns.tolist()
        
        # Mapping generic MT5 headers
        col_map = {
            'Time': 'entry_time', 'Time.1': 'exit_time',
            'Symbol': 'symbol', 'Type': 'trade_type',
            'Volume': 'lot_size', 'Profit': 'profit_loss',
            'Commission': 'commission', 'Ticket': 'ticket_number'
        }
        
        available_cols = [c for c in col_map.keys() if c in cols]
        if not available_cols: return []
        
        for index, row in df.iterrows():
            t_data = {}
            try:
                for col in available_cols:
                    val = row[col]
                    if 'time' in col.lower():
                        val = pd.to_datetime(val)
                    elif 'volume' in col.lower():
                        val = float(str(val).replace(',', '.'))
                    elif isinstance(val, str) and ('profit' in col.lower() or 'commission' in col.lower()):
                        val = float(val.replace(',', '.'))
                    
                    t_data[col_map[col]] = val
                
                if 'entry_time' in t_data and 'exit_time' in t_data:
                    trades.append(t_data)
            except:
                continue
    except Exception as e:
        print(f"Parser Error: {e}")
    return trades

# === 3. API APP ===
app = FastAPI(title="Trading Journal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/upload-history/")
async def upload_history(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    parsed_trades = parse_mt5_file(content, file.filename)
    
    if not parsed_trades:
        return {"error": "Could not parse file or no valid trades found."}

    saved_trades = []
    user_id = 1 
    
    for t in parsed_trades:
        trade = Trade(
            user_id=user_id,
            ticket_number=t.get('ticket_number'),
            symbol=t['symbol'],
            entry_time=t['entry_time'],
            exit_time=t['exit_time'],
            trade_type=t['trade_type'],
            lot_size=t['lot_size'],
            profit_loss=t['profit_loss'],
            commission=t.get('commission', 0)
        )
        db.add(trade)
        saved_trades.append(trade)
    
    db.commit()
    return {"message": f"Imported {len(saved_trades)} trades successfully"}

@app.get("/trades/")
def get_trades(db: Session = Depends(get_db)):
    trades = db.query(Trade).all()
    return [{
        "id": t.id, "symbol": t.symbol,
        "entry_time": t.entry_time.isoformat(),
        "exit_time": t.exit_time.isoformat(),
        "trade_type": t.trade_type,
        "lot_size": t.lot_size,
        "profit_loss": float(t.profit_loss),
        "notes": t.notes
    } for t in trades]

@app.get("/analytics/")
def get_analytics(db: Session = Depends(get_db)):
    trades = db.query(Trade).all()
    if not trades:
        return {"total_trades": 0, "win_rate": 0, "total_pnl": 0, "profit_factor": 0}
    
    wins = [t for t in trades if float(t.profit_loss) > 0]
    losses = [t for t in trades if float(t.profit_loss) <= 0]
    
    total_pnl = sum([float(t.profit_loss) for t in trades])
    win_rate = (len(wins) / len(trades)) * 100
    
    gross_profit = sum([float(t.profit_loss) for t in wins])
    gross_loss = abs(sum([float(t.profit_loss) for t in losses]))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    # Drawdown Calc
    running, peak, max_dd = 0, 0, 0
    for t in trades:
        running += float(t.profit_loss)
        if running > peak: peak = running
        dd = peak - running
        if dd > max_dd: max_dd = dd

    return {
        "total_trades": len(trades), "wins": len(wins),
        "losses": len(losses), "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_dd, 2)
    }

@app.post("/trades/{trade_id}/note/")
async def add_note(trade_id: int, note: str = Form(...), db: Session = Depends(get_db)):
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade: raise HTTPException(status_code=404, detail="Trade not found")
    trade.notes = note
    db.commit()
    return {"message": "Note saved"}

@app.post("/trades/{trade_id}/screenshot/")
async def upload_screenshot(trade_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade: raise HTTPException(status_code=404, detail="Trade not found")
    
    file_ext = file.filename.split(".")[-1]
    file_name = f"{trade_id}_{secrets.token_hex(4)}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    att = TradeAttachment(trade_id=trade_id, file_name=file.filename, file_path=file_path)
    db.add(att)
    db.commit()
    return {"message": "Image uploaded"}

@app.get("/")
def read_root():
    return {"msg": "Trading Journal API running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
