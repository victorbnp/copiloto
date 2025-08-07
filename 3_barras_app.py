import MetaTrader5 as mt5
import pandas as pd
from random import randrange
import time
import numpy as np
from datetime import datetime, timedelta


# Inicializa conexão com MT5
if not mt5.initialize():
    print("Erro ao inicializar MT5")
    quit()

### Variáveis de inicialização ###    
# Símbolo do ativo que vai operar
simbolo = "WINQ25"  
# Timeframe a ser usado, pode ser alterado para M5, M15, H1 etc.
timeframe = mt5.TIMEFRAME_M30  
# Número de velas para carregar
num_barras = 5
# Número de contratos a ser usado para operar
num_contratos = 1
# Horário para encerrar as negociações
hora_fim_operacoes = 18
# Horário da barra negociada
hora_entrada_operacao = None 


#Função para abrir ordem a mercado
def coloca_ordem_mercado(type,symbol,position_length):
    if (type == 'buy'):
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(position_length),
            "type": mt5.ORDER_TYPE_BUY,
            "deviation": 20,
            "magic": randrange(1000000),
            "comment": "python script open",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }    
        mt5.order_send(request)
    else:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(position_length),
            "type": mt5.ORDER_TYPE_SELL,
            "deviation": 20,
            "magic": randrange(1000000),
            "comment": "python script open",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }
        mt5.order_send(request)

# Sai de todas as posições abertas
def encerra_todas_posicoes(symbol):
    resultPositions = mt5.positions_get()

    if len(resultPositions) > 0:
        if resultPositions[0].type == 0:
            coloca_ordem_mercado('sell',symbol,resultPositions[0].volume)
        elif resultPositions[0].type == 1:
            coloca_ordem_mercado('buy',symbol,resultPositions[0].volume)

while True:
    # Carrega dados do mercado
    rates = mt5.copy_rates_from_pos(simbolo, timeframe, 0, num_barras)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    # Identifica se cada barra é compradora ou vendedora
    df['barra_compradora'] = df['close'] > df['open']
    df['barra_vendedora'] = df['close'] < df['open']

    # Conta sequências de 3 barras consecutivas
    df['barra_compradora_count'] = df['barra_compradora'][:-1].rolling(window=3).sum() == 3
    df['barra_vendedora_count'] = df['barra_vendedora'][:-1].rolling(window=3).sum() == 3

    # Marca se deve comprar, vender ou nada a fazer
    deve_comprar = df['barra_compradora_count'].iloc[-2]
    deve_vender = df['barra_vendedora_count'].iloc[-2]

    posicoes = mt5.positions_get(symbol=simbolo)
    if posicoes:
        df["time"].iloc[-2]

    if (not posicoes):
        if deve_comprar:
            coloca_ordem_mercado('buy',simbolo,num_contratos)
            hora_entrada_operacao = df["time"].iloc[-2]
        elif deve_vender:
            coloca_ordem_mercado('sell',simbolo,num_contratos)
            hora_entrada_operacao = df["time"].iloc[-2]

        #print(' ')
    else:
        if posicoes[0].type == 0 and deve_vender and hora_entrada_operacao < df["time"].iloc[-2]:
            encerra_todas_posicoes(simbolo)
            print('saiu compra: ', df["time"].iloc[-2])
        elif posicoes[0].type == 1 and deve_comprar and hora_entrada_operacao < df["time"].iloc[-2]:
            encerra_todas_posicoes(simbolo)
            print('saiu venda: ', df["time"].iloc[-2])
    #print(' ')
    time.sleep(1)