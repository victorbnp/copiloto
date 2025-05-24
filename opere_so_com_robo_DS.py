import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timedelta
import time

# Configurações
SYMBOL = "WIN$"
TIMEFRAME_SEC = 30  # Timeframe personalizado de 30 segundos
EMA_PERIOD = 9
RISK_REWARD = 2
LOTE = 1
PONTOS_POR_PIP = 1
MAX_BAR_SIZE_RATIO = 3

def conectar_mt5():
    if not mt5.initialize():
        print("Erro ao conectar ao MT5:", mt5.last_error())
        return False
    return True

def criar_timeframe_30s():
    agora = datetime.now()
    return [agora - timedelta(seconds=(x*TIMEFRAME_SEC)) for x in range(200)][::-1]

def obter_ticks_30s(symbol):
    ticks = mt5.copy_ticks_from(symbol, datetime.now(), 1000, mt5.COPY_TICKS_ALL)
    return pd.DataFrame(ticks)[['time', 'ask', 'bid']]

def processar_barras_30s(ticks):
    ticks['time'] = pd.to_datetime(ticks['time'], unit='s')
    ticks['preco'] = (ticks['ask'] + ticks['bid']) / 2
    return ticks.resample(f'{TIMEFRAME_SEC}S', on='time').agg(
        {'preco': 'ohlc', 'ask': 'last', 'bid': 'last'}).dropna()

def calcular_ema(df):
    df['EMA'] = df['preco']['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    df['EMA_diff'] = df['EMA'].diff()
    return df

def identificar_pivots(df):
    df['doji'] = np.where(df['preco']['high'] == df['preco']['low'], 1, 0)
    df = df[df['doji'] == 0].copy()
    
    df['topo'] = np.where((df['preco']['close'].shift(1) > df['preco']['close'].shift(2)) & 
                        (df['preco']['close'] < df['preco']['close'].shift(1)), 1, 0)
    
    df['fundo'] = np.where((df['preco']['close'].shift(1) < df['preco']['close'].shift(2)) & 
                         (df['preco']['close'] > df['preco']['close'].shift(1)), 1, 0)
    return df

def verificar_tamanho_barra(df):
    df['tamanho'] = abs(df['preco']['close'] - df['preco']['open'])
    media_7 = df['tamanho'].rolling(7).mean()
    return df['tamanho'] < (media_7 * MAX_BAR_SIZE_RATIO)

def gerenciar_ordens(posicao, risco_pontos):
    if posicao:
        if posicao.profit_pips >= risco_pontos * RISK_REWARD:
            mt5.Close(posicao.ticket)
        elif posicao.profit_pips >= risco_pontos:
            mt5.modify(posicao.ticket, sl=posicao.price_open)

def executar_estrategia():
    if not conectar_mt5():
        return
    
    while True:
        ticks = obter_ticks_30s(SYMBOL)
        barras = processar_barras_30s(ticks)
        barras = calcular_ema(barras)
        barras = identificar_pivots(barras)
        barras['valida_tamanho'] = verificar_tamanho_barra(barras)
        
        ultima_barra = barras.iloc[-1]
        penultima_barra = barras.iloc[-2]
        
        sinal_compra = (ultima_barra['EMA_diff'] > 0 and penultima_barra['EMA_diff'] < 0 and
                       ultima_barra['preco']['close'] > barras[barras['topo'] == 1]['preco']['high'].iloc[-1] and
                       ultima_barra['valida_tamanho'])
        
        sinal_venda = (ultima_barra['EMA_diff'] < 0 and penultima_barra['EMA_diff'] > 0 and
                      ultima_barra['preco']['close'] < barras[barras['fundo'] == 1]['preco']['low'].iloc[-1] and
                      ultima_barra['valida_tamanho'])
        
        if sinal_compra:
            stop_loss = penultima_barra['preco']['low']
            take_profit = ultima_barra['preco']['close'] + (ultima_barra['preco']['close'] - stop_loss) * RISK_REWARD
            mt5.Buy(LOTE, SYMBOL, ultima_barra['ask']['last'], stop_loss, take_profit)
            
        elif sinal_venda:
            stop_loss = penultima_barra['preco']['high']
            take_profit = ultima_barra['preco']['close'] - (stop_loss - ultima_barra['preco']['close']) * RISK_REWARD
            mt5.Sell(LOTE, SYMBOL, ultima_barra['bid']['last'], stop_loss, take_profit)
        
        # Gerenciamento de ordens ativas
        posicoes = mt5.positions_get(symbol=SYMBOL)
        for pos in posicoes:
            risco = abs(pos.price_open - pos.sl)
            gerenciar_ordens(pos, risco)
        
        time.sleep(TIMEFRAME_SEC)

if __name__ == "__main__":
    executar_estrategia()