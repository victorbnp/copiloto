import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time

# ====== CONFIGURAÇÕES ======
SYMBOL = "WINM25"  # Altere conforme o ativo
LOT = 1.0
TIMEFRAME = mt5.TIMEFRAME_M1  # 30 segundos
MAGIC_NUMBER = 123456

# Conectar ao MetaTrader 5
if not mt5.initialize():
    print("initialize() failed", mt5.last_error())
    quit()

def get_data(symbol, n_bars=100):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n_bars)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def calculate_indicators(df):
    df['ema9'] = df['close'].ewm(span=9).mean()
    df['ema9_diff'] = df['ema9'] - df['ema9'].shift(1)
    df['sma20'] = df['close'].rolling(window=20).mean()
    df['sma20_diff'] = df['sma20'] - df['sma20'].shift(1)
    df['body_size'] = abs(df['close'] - df['open'])
    df['avg_body_7'] = df['body_size'].rolling(7).mean()
    df['bar_ok'] = df['body_size'] < df['avg_body_7'] * 3
    return df

def detect_pivot_highs_lows(close_series, open_series):
    topos = []
    fundos = []

    clean_closes = []
    valid_indices = []

    for i in range(len(close_series)):
        if close_series[i] != open_series[i]:
            clean_closes.append(close_series[i])
            valid_indices.append(i)

    for j in range(1, len(clean_closes) - 1):
        prev = clean_closes[j - 1]
        curr = clean_closes[j]
        next = clean_closes[j + 1]
        idx = valid_indices[j]

        if curr > prev and curr > next:
            topos.append((idx, curr))
        if curr < prev and curr < next:
            fundos.append((idx, curr))

    return topos, fundos

def get_last_topo_fundo(df):
    closes = df['close'].values
    opens = df['open'].values
    topos, fundos = detect_pivot_highs_lows(closes, opens)

    last_topo = topos[-1][1] if topos else None
    last_fundo = fundos[-1][1] if fundos else None

    df['ultimo_topo'] = last_topo
    df['ultimo_fundo'] = last_fundo

    return df

def ema_virou(df):
    # Verifica mudança de inclinação da EMA
    return (df['ema9_diff'].iloc[-2] < 0 and df['ema9_diff'].iloc[-1] > 0) or \
           (df['ema9_diff'].iloc[-2] > 0 and df['ema9_diff'].iloc[-1] < 0)

def find_entry(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if not last['bar_ok']:
        return None

    if ema_virou(df):
        # CONDIÇÃO DE COMPRA
        if df['ema9_diff'].iloc[-2] < 0 and df['ema9_diff'].iloc[-1] > 0:
            if last['close'] > last['ultimo_topo'] and last['sma20'] > prev['sma20']:
                return 'buy'
        # CONDIÇÃO DE VENDA
        elif df['ema9_diff'].iloc[-2] > 0 and df['ema9_diff'].iloc[-1] < 0:
            if last['close'] < last['ultimo_fundo'] and last['sma20'] < prev['sma20']:
                return 'sell'

    return None


def send_order(entry_price, sl_price, tp_price, direction="buy", lot=LOT):
    symbol = SYMBOL
    if not mt5.symbol_select(symbol, True):
        print(f"Erro ao selecionar símbolo {symbol}")
        return None

    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        print("Erro ao obter informações do símbolo")
        return None

    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if direction.lower() == "buy" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction.lower() == "buy" else mt5.ORDER_TYPE_SELL
    filling_type = symbol_info.trade_fill_mode
    point = symbol_info.point
    stops_level = symbol_info.trade_stops_level

    # Verifica se SL e TP estão suficientemente distantes
    if direction == 'buy':
        if (price - sl_price) < (stops_level * point):
            sl_price = price - (stops_level + 5) * point
        if (tp_price - price) < (stops_level * point):
            tp_price = price + (stops_level + 5) * point
    else:
        if (sl_price - price) < (stops_level * point):
            sl_price = price + (stops_level + 5) * point
        if (price - tp_price) < (stops_level * point):
            tp_price = price - (stops_level + 5) * point

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl_price,
        "tp": tp_price,
        "deviation": 10,
        "magic": MAGIC_NUMBER,
        "comment": "Ordem enviada por script",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_type,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Erro ao enviar ordem: {result.retcode} - {result.comment}")
        return None

    print(f"Ordem enviada com sucesso: {result}")
    return result


# ====== LOOP PRINCIPAL ======
print("Iniciando monitoramento...")

ultima_entrada = None
ticket_aberto = None

while True:
    df = get_data(SYMBOL)
    df = calculate_indicators(df)
    df = get_last_topo_fundo(df)

    entry = find_entry(df)
    timestamp_ultima_barra = df.index[-1]

    if entry and ultima_entrada != timestamp_ultima_barra and not ticket_aberto:
        last_closed = df.iloc[-2]  # Última barra fechada
        sl = last_closed['low'] if entry == 'buy' else last_closed['high']
        risk = abs(last_closed['close'] - sl)
        tp = last_closed['close'] + 2 * risk if entry == 'buy' else last_closed['close'] - 2 * risk

        result = send_order(last_closed['close'], sl, tp, entry)

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            ticket_aberto = result.order
            ultima_entrada = timestamp_ultima_barra
            # Aqui você pode iniciar uma função de gerenciamento de trade se desejar
        else:
            print(f"Erro ao enviar ordem: {result}")
        ultima_entrada = timestamp_ultima_barra

    time.sleep(1)
