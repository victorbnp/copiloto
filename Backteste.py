import pandas as pd
import MetaTrader5 as mt5

# ─── CONFIGURAÇÕES DE BACKTEST ─────────────────────────────────────────────────
SYMBOL      = "WINM25"
TIMEFRAME   = mt5.TIMEFRAME_M1
BAR_COUNT   = 360           # número de barras de sinal (ontem)
EXTRA_BARS  = 60            # barras extras para indicadores e swing
LOT_SIZE    = 50.0          # unidades por operação
PARTIAL_PCT = 0.5           # 50% no primeiro parcial

# ─── INICIALIZAÇÃO MT5 ─────────────────────────────────────────────────────────
def initialize_mt5():
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize falhou: {mt5.last_error()}")

# ─── OBTÉM ÚLTIMAS BARRAS ───────────────────────────────────────────────────────
def fetch_last_bars(symbol, timeframe, total_count):
    """
    Busca as últimas 'total_count' barras fechadas (exclui barra em formação).
    Usa mt5.copy_rates_from, pulando a barra atual (pos=1).
    """
    rates = mt5.copy_rates_from(symbol, timeframe, 1, total_count)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

# ─── INDICADORES E SINAIS ─────────────────────────────────────────────────────────
def compute_indicators(df):
    df['body']  = (df['close'] - df['open']).abs()
    df['ema9']  = df['close'].ewm(span=9, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    return df

# ─── SWING HIGH/LOW ─────────────────────────────────────────────────────────────
def get_last_swing_high(df, idx):
    # janela até idx (exclui idx)
    window = df.iloc[max(0, idx-EXTRA_BARS-1):idx].copy().reset_index()
    window = window[window['open'] != window['close']]
    n = len(window)
    if n < 3:
        return None
    for i in range(n-2, -1, -1):
        c = window.at[i, 'close']
        prev = window.at[i-1, 'close'] if i-1>=0 else None
        nxt  = window.at[i+1, 'close']
        if (prev is None or c > prev) and c > nxt:
            return c
    return None

def get_last_swing_low(df, idx):
    window = df.iloc[max(0, idx-EXTRA_BARS-1):idx].copy().reset_index()
    window = window[window['open'] != window['close']]
    n = len(window)
    if n < 3:
        return None
    for i in range(n-2, -1, -1):
        c = window.at[i, 'close']
        prev = window.at[i-1, 'close'] if i-1>=0 else None
        nxt  = window.at[i+1, 'close']
        if (prev is None or c < prev) and c < nxt:
            return c
    return None

# ─── BACKTEST ────────────────────────────────────────────────────────────────────
def backtest():
    initialize_mt5()
    total_bars = BAR_COUNT + EXTRA_BARS
    data = fetch_last_bars(SYMBOL, TIMEFRAME, total_bars)
    if data.empty:
        print("Nenhum dado retornado. Verifique conexão e símbolo.")
        return
    df = compute_indicators(data)

    equity = 0.0
    trades = []
    start_idx = EXTRA_BARS  # só começa após ter barras extras para cálculo

    for i in range(start_idx, len(df)):
        # só processa sinais nas últimas BAR_COUNT barras
        if i < len(df) - BAR_COUNT:
            continue
        sub = df.iloc[:i+1]
        # EMA9 reversão
        slope1 = sub['ema9'].iloc[-2] - sub['ema9'].iloc[-3]
        slope2 = sub['ema9'].iloc[-1] - sub['ema9'].iloc[-2]
        rev_up   = slope1 < 0 and slope2 > 0
        rev_down = slope1 > 0 and slope2 < 0

        # descarta barras extremas
        last_body = sub['body'].iloc[-1]
        avg7      = sub['body'].iloc[-8:-1].mean()
        if not (rev_up or rev_down) or last_body > 3 * avg7:
            continue

        # filtro EMA20
        ema20_slope = sub['ema20'].iloc[-1] - sub['ema20'].iloc[-2]
        if rev_up and ema20_slope <= 0 or rev_down and ema20_slope >= 0:
            continue

        last_high = get_last_swing_high(df, i)
        last_low  = get_last_swing_low(df, i)
        close0    = sub['close'].iloc[-1]

        side = None
        if rev_up and last_high and close0 > last_high:
            side = 'buy';  stop = sub['low'].iloc[-2]
        elif rev_down and last_low and close0 < last_low:
            side = 'sell'; stop = sub['high'].iloc[-2]
        if not side:
            continue

        entry = close0
        risk  = abs(entry - stop)
        tp1   = entry + risk * (1 if side=='buy' else -1)
        tp2   = entry + risk * (2 if side=='buy' else -2)

        trade = {'entry':entry,'side':side,'stop':stop,'tp1':tp1,'tp2':tp2,'vol':LOT_SIZE,'p1':False}

        # gestão
        for j in range(i+1, len(df)):
            low  = df['low'].iloc[j]
            high = df['high'].iloc[j]
            if (side=='buy' and low <= trade['stop']) or (side=='sell' and high >= trade['stop']):
                pnl = (trade['stop'] - entry) * LOT_SIZE if side=='buy' else (entry - trade['stop']) * LOT_SIZE
                equity += pnl; break
            if not trade['p1'] and ((side=='buy' and high >= tp1) or (side=='sell' and low <= tp1)):
                equity += (tp1-entry)*LOT_SIZE*PARTIAL_PCT if side=='buy' else (entry-tp1)*LOT_SIZE*PARTIAL_PCT
                trade['stop'] = entry; trade['p1'] = True
            if trade['p1']:
                trade['stop'] = max(trade['stop'], low) if side=='buy' else min(trade['stop'], high)
            if trade['p1'] and ((side=='buy' and high >= tp2) or (side=='sell' and low <= tp2)):
                equity += (tp2-entry)*LOT_SIZE*(1-PARTIAL_PCT) if side=='buy' else (entry-tp2)*LOT_SIZE*(1-PARTIAL_PCT)
                break
        trades.append(trade)

    print(f"Backtest: {len(trades)} trades | Equity final: R$ {equity:.2f}")
    mt5.shutdown()

if __name__=='__main__':
    backtest()
