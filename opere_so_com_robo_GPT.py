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

    #print('topo: ', last_topo ,' fundo: ', last_fundo)

    return df

def find_entry(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if not last['bar_ok']:
        return None

    if prev['ema9_diff'] < 0 and last['ema9_diff'] > 0:
        if last['close'] > last['ultimo_topo']:
            return 'buy'

    if prev['ema9_diff'] > 0 and last['ema9_diff'] < 0:
        if last['close'] < last['ultimo_fundo']:
            return 'sell'

    return None

def send_order(entry_price, sl_price, tp_price, direction="buy", lot=LOT):
    symbol = SYMBOL
    # Verifique se o símbolo está habilitado
    if not mt5.symbol_select(symbol, True):
        print(f"Erro ao selecionar símbolo {symbol}")
        return None

    # Define o tipo de ordem
    order_type = mt5.ORDER_TYPE_BUY if direction.lower() == "buy" else mt5.ORDER_TYPE_SELL

    # Define o tipo de preenchimento
    symbol_info = mt5.symbol_info(symbol)
    filling_type = mt5.ORDER_FILLING_IOC

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": mt5.symbol_info_tick(symbol).ask if direction == "buy" else mt5.symbol_info_tick(symbol).bid,
        "sl": sl_price,
        "tp": tp_price,
        "deviation": 10,
        "magic": 123456,
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


def manage_trade(ticket, direction, sl, tp, entry_price):
    while True:
        # Obter a posição aberta
        position = mt5.positions_get(ticket=ticket)
        if not position:
            print("Posição não encontrada, encerrando gerenciamento.")
            break

        position = position[0]
        current_price = position['price_open'] if direction == 'buy' else position['price_open']
        stop_loss = position['sl']
        take_profit = position['tp']
        order_type = position['type']
        volume = position['volume']

        # Atingir 1:1 do risco (parcial)
        risk = abs(entry_price - sl)
        target = entry_price + risk if direction == 'buy' else entry_price - risk
        if (direction == 'buy' and current_price >= target) or (direction == 'sell' and current_price <= target):
            partial_exit = volume * 0.5
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": partial_exit,
                "type": order_type,
                "price": current_price,
                "sl": stop_loss,
                "tp": take_profit,
                "magic": MAGIC_NUMBER,
                "comment": "Parcial 1:1"
            })
            print("Parcial 1:1 executada.")
            # Move o stop para breakeven
            stop_loss = entry_price if direction == 'buy' else entry_price
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": volume - partial_exit,
                "type": order_type,
                "price": current_price,
                "sl": stop_loss,
                "tp": take_profit,
                "magic": MAGIC_NUMBER,
                "comment": "Atualização do stop para breakeven"
            })
            print("Stop movido para breakeven.")

        # Trailing Stop - Mínima/Máxima das barras
        if direction == 'buy':
            trailing_stop = max(position['low'], current_price)  # Maior preço no caso de compra
        else:
            trailing_stop = min(position['high'], current_price)  # Menor preço no caso de venda

        if trailing_stop != stop_loss:
            stop_loss = trailing_stop
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": volume,
                "type": order_type,
                "price": current_price,
                "sl": stop_loss,
                "tp": take_profit,
                "magic": MAGIC_NUMBER,
                "comment": "Atualização do trailing stop"
            })
            print(f"Trailing stop ajustado: {stop_loss}")

        time.sleep(10)  # Esperar 10 segundos antes de verificar novamente

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
        last = df.iloc[-1]
        sl = last['low'] if entry == 'buy' else last['high']
        risk = abs(last['close'] - sl)
        tp = last['close'] + 2 * risk if entry == 'buy' else last['close'] - 2 * risk
    
        result = send_order(entry, sl, tp)

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            ticket_aberto = result.order
            ultima_entrada = timestamp_ultima_barra
            manage_trade(ticket_aberto, entry, sl, tp, last['close'])
        else:
            print(f"Erro ao enviar ordem: {result}")
        ultima_entrada = timestamp_ultima_barra

    time.sleep(1)  # Checar a cada 5 segundos
