import time
import MetaTrader5 as mt5
import pandas as pd

# ─── CONFIGURAÇÕES ─────────────────────────────────────────────────────────────
SYMBOL       = "WINM25"                 # símbolo do mini-índice
TIMEFRAME    = mt5.TIMEFRAME_M1       # timeframe (mude para M1, M15, etc.)
LOT_SIZE     = 50.0                    # tamanho do lote por operação
PARTIAL_PCT  = 0.5                    # 50% no primeiro parcial
MAGIC_NUMBER = 123456
SLEEP_SECS   = 1                     # aguarda 60s entre verificações

# ─── FUNÇÕES AUXILIARES ────────────────────────────────────────────────────────

def initialize_mt5():
    if not mt5.initialize():
        print("Falha ao inicializar MT5:", mt5.last_error())
        mt5.shutdown()
        exit()

def get_ohlc(symbol, timeframe, n=100):
    """Retorna DataFrame com as últimas n barras."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
    df = pd.DataFrame(rates)
    df['time']   = pd.to_datetime(df['time'], unit='s')
    df['body']   = (df['close'] - df['open']).abs()
    df['ema9']   = df['close'].ewm(span=9, adjust=False).mean()
    df['ema20']  = df['close'].ewm(span=20, adjust=False).mean()
    return df

def is_extreme_bar(df):
    """Retorna True se a última barra for >3x corpo médio das 7 anteriores."""
    last_body = df['body'].iloc[-1]
    avg7      = df['body'].iloc[-8:-1].mean()
    return last_body > 3 * avg7

def get_last_swing_high(df):
    """Último topo: último fechamento > fechamento seguinte, ignorando dojis."""
    tmp = df[df['open'] != df['close']].reset_index(drop=True)
    for i in range(len(tmp)-2, -1, -1):
        if tmp.at[i, 'close'] > tmp.at[i+1, 'close']:
            return tmp.at[i, 'close']
    return None

def get_last_swing_low(df):
    """Último fundo: último fechamento < fechamento seguinte, ignorando dojis."""
    tmp = df[df['open'] != df['close']].reset_index(drop=True)
    for i in range(len(tmp)-2, -1, -1):
        if tmp.at[i, 'close'] < tmp.at[i+1, 'close']:
            return tmp.at[i, 'close']
    return None

def send_market_order(symbol, side, volume):
    """Envia ordem a mercado de compra (side= 'buy') ou venda ('sell')."""
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if side=='buy' else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if side=='buy' else mt5.ORDER_TYPE_SELL
    request = {
        "action":     mt5.TRADE_ACTION_DEAL,
        "symbol":     symbol,
        "volume":     volume,
        "type":       order_type,
        "price":      price,
        "deviation":  10,
        "magic":      MAGIC_NUMBER,
        "comment":    "EMA9 Reversal",
        "type_time":  mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("Erro ao enviar ordem:", result)
        return None
    return result.order

def close_position(ticket, volume):
    """Fecha parte ou total de posição identificada por ticket."""
    pos = mt5.positions_get(ticket=ticket)[0]
    side = 'sell' if pos.type==mt5.POSITION_TYPE_BUY else 'buy'
    return send_market_order(pos.symbol, side, volume)

def get_last_swing_high(df):
    """
    Último topo (swing high) em até 50 barras fechadas:
     - descarta a barra corrente e dojis
     - retorna o último fechamento que seja maior que ambos vizinhos
       (ou, no índice 0, maior que o próximo).
    """
    window = df.iloc[-51:].copy().reset_index(drop=True)
    # descarta a barra corrente
    window = window.iloc[:-1]
    # remove dojis
    window = window[window['open'] != window['close']].reset_index(drop=True)

    n = len(window)
    if n < 2:
        return None

    # percorre de trás pra frente (do mais recente ao mais antigo)
    for i in range(n-1, -1, -1):
        c = window.at[i, 'close']
        if i == 0:
            # ponta esquerda: só compara com o próximo
            if c > window.at[i+1, 'close']:
                return c
        elif i == n-1:
            # ponta direita (seria o penúltimo original): só compara com o anterior
            if c > window.at[i-1, 'close']:
                return c
        else:
            # interior: compara ambos vizinhos
            if c > window.at[i-1, 'close'] and c > window.at[i+1, 'close']:
                return c
    return None


def get_last_swing_low(df):
    """
    Último fundo (swing low) em até 50 barras fechadas:
     - descarta a barra corrente e dojis
     - retorna o último fechamento que seja menor que ambos vizinhos
       (ou, no índice 0, menor que o próximo).
    """
    window = df.iloc[-51:].copy().reset_index(drop=True)
    window = window.iloc[:-1]
    window = window[window['open'] != window['close']].reset_index(drop=True)

    n = len(window)
    if n < 2:
        return None

    for i in range(n-1, -1, -1):
        c = window.at[i, 'close']
        if i == 0:
            # ponta esquerda
            if c < window.at[i+1, 'close']:
                return c
        elif i == n-1:
            # ponta direita
            if c < window.at[i-1, 'close']:
                return c
        else:
            # interior
            if c < window.at[i-1, 'close'] and c < window.at[i+1, 'close']:
                return c
    return None




# ─── LOOP PRINCIPAL COM DETECÇÃO DE NOVA BARRA ─────────────────────────────────

initialize_mt5()
open_trades = {}
last_bar_time = None

while True:
    df = get_ohlc(SYMBOL, TIMEFRAME, n=100)
    # timestamp da última barra fechada
    cur_bar_time = df['time'].iloc[-1]
    
    #print('topo: ', get_last_swing_high(df))
    #print('fundo: ',get_last_swing_low(df))

    # se não houver barra nova, pula diretamente para gestão de trades
    if 1 == 1: #cur_bar_time != last_bar_time:
        # ─── SINAL DE ENTRADA (SÓ EM NOVA BARRA FECHADA) ────────────────────────
        # slope da EMA9 usando apenas barras fechadas
        print()
        print(df['ema9'].iloc[-2], df['ema9'].iloc[-3], df['ema9'].iloc[-4])
        slope1 = df['ema9'].iloc[-2] - df['ema9'].iloc[-3]
        slope2 = df['ema9'].iloc[-1] - df['ema9'].iloc[-2]

        rev_up = df['ema9'].iloc[-4] > df['ema9'].iloc[-3] < df['ema9'].iloc[-2]
        print('rev_up: ', rev_up)
        rev_down = df['ema9'].iloc[-4] < df['ema9'].iloc[-3] > df['ema9'].iloc[-2]
        print('rev_down: ', rev_down)

        # descarta barra extrema (corpo >3× média das últimas 7)
        if (rev_up or rev_down) and not is_extreme_bar(df):
            # inclinação da EMA20 só com barras fechadas
            ema20_slope = df['ema20'].iloc[-1] - df['ema20'].iloc[-2]
            if (rev_up   and ema20_slope > 0) or \
               (rev_down and ema20_slope < 0):
            #if (rev_up) or \
            #   (rev_down):                

                # últimos topo/fundo calculados até penúltima barra
                last_high = get_last_swing_high(df)
                last_low  = get_last_swing_low(df)
                close0    = df['close'].iloc[-1]

                if rev_up and last_high and close0 > last_high:
                    side = 'buy'
                    stop = df['low'].iloc[-2]
                elif rev_down and last_low and close0 < last_low:
                    side = 'sell'
                    stop = df['high'].iloc[-2]
                else:
                    side = None

                if side:
                    entry = close0
                    risk  = abs(entry - stop)
                    tp1   = entry + risk * (1 if side=='buy' else -1)
                    tp2   = entry + risk * (2 if side=='buy' else -2)
                    ticket = send_market_order(SYMBOL, side, LOT_SIZE)
                    if ticket:
                        open_trades[ticket] = {
                            "side": side, "entry": entry, "stop": stop,
                            "tp1": tp1, "tp2": tp2,
                            "vol_rem": LOT_SIZE, "p1_done": False
                        }
                        print(f"[{time.ctime()}] Entrada {side} @ {entry:.2f}, SL {stop:.2f}, TP1 {tp1:.2f}, TP2 {tp2:.2f}")

        # atualiza o marcador de última barra processada
        last_bar_time = cur_bar_time



    # ─── GESTÃO DE TRADES ABERTOS (pode rodar a cada tick/secs) ───────────────
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.bid if rev_up else tick.ask  # preço de referência genérico
    # usa preço de bid/ask conforme lado
    for ticket, info in list(open_trades.items()):
        side      = info['side']
        entry     = info['entry']
        stop      = info['stop']
        tp1, tp2  = info['tp1'], info['tp2']
        rem       = info['vol_rem']
        p1_done   = info['p1_done']
        
        # 1) Stop-loss
        if (side=='buy'  and price <= stop) or \
           (side=='sell' and price >= stop):
            close_position(ticket, rem)
            print(f"[{time.ctime()}] SL atingido. Ticket {ticket} fechado totalmente.")
            del open_trades[ticket]
            continue
        
        # 2) Primeiro parcial (1R)
        if not p1_done and ((side=='buy'  and price >= tp1) or
                            (side=='sell' and price <= tp1)):
            vol_p1 = rem * PARTIAL_PCT
            close_position(ticket, vol_p1)
            # move stop para breakeven
            info['stop']      = entry
            info['vol_rem']  -= vol_p1
            info['p1_done']   = True
            print(f"[{time.ctime()}] 1º parcial ({vol_p1:.2f}) em {tp1:.2f}. SL para BE.")
            rem = info['vol_rem']
        
        # 3) Trailing stop após 1º parcial
        if p1_done and rem > 0:
            # usar mínima/máxima da barra anterior
            bar = df.iloc[-2]
            new_stop = max(info['stop'], bar['low']) if side=='buy' else min(info['stop'], bar['high'])
            info['stop'] = new_stop
        
        # 4) Segundo parcial (2R)
        if p1_done and ((side=='buy'  and price >= tp2) or
                        (side=='sell' and price <= tp2)):
            close_position(ticket, rem)
            print(f"[{time.ctime()}] 2º parcial ({rem:.2f}) em {tp2:.2f}. Operação encerrada.")
            del open_trades[ticket]

    time.sleep(SLEEP_SECS)






















