
from datetime import datetime
import MetaTrader5 as mt5
from random import randrange
import time
import pandas as pd

def format_rates(ativo, timeframe, qtd_candles=5):
    rates = mt5.copy_rates_from_pos(ativo, timeframe, 1, qtd_candles)
    rates_dt = pd.DataFrame(rates)
    rates_dt['time'] = pd.to_datetime(rates_dt['time'], unit='s')
    rates_dt.set_index('time', inplace=True)
    return rates_dt

def put_order(type,symbol,position_length):
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

#Sainda de uma posição
def leave_position(symbol_win):
    resultPositions = mt5.positions_get()

    if len(resultPositions) > 0:
        if resultPositions[0].type == 0:
            put_order('sell',symbol_win,resultPositions[0].volume)
        elif resultPositions[0].type == 1:
            put_order('buy',symbol_win,resultPositions[0].volume)

def get_day_result():

    hoje = datetime(datetime.now().year,datetime.now().month,datetime.now().day)
    hoje_fim = datetime(datetime.now().year,datetime.now().month,datetime.now().day,23)
    dayResults = mt5.history_deals_get(hoje, hoje_fim)
    balance = 0.0

    if len(dayResults)>0:
        for v in dayResults:
            if (v.type != 2):
                balance = balance + v.profit
                balance = balance - (v.volume * 0.25)

    print()
    return balance  #if balance <= 0 else balance - (balance * 0.01)        

#Sai de uma posição quando ultrapassar média móvel
def build_cross_avg_signal_list(symbol,status_order, ativo, window=20):
    media_movel = ativo.close.rolling(window=window).mean()
    last_tick = mt5.symbol_info_tick(symbol)
    resultPositions = mt5.positions_get()
    print(last_tick.last, media_movel[-1])

    if len(resultPositions) > 0:
        #compra
        if resultPositions[0].type == 0:
            if last_tick.last <= media_movel[-1]:
                print('sair')
                leave_position(symbol)
        elif resultPositions[0].type == 1:
            if last_tick.last >= media_movel[-1]:
                print('sair')
                leave_position(symbol)

def main():
    status_order = None
    
    ######################parâmetros######################
    symbol = 'CRFB3'
    stop = -900
    sair_stop = False
    rastrear_media_movel = True
    #######################################################

    if mt5.initialize():
        while 1==1:
            
            if sair_stop:
                #time.sleep(0.56)
                dayResult = get_day_result()
                resultPositions = mt5.positions_get()
                in_operation = True if len(resultPositions) > 0 else False
                if in_operation:
                    aux = (dayResult + (resultPositions[0].profit)) #+ (resultPositions[0].volume * -0.25)) 
                    print('Valor + op:',aux if aux <= 0 else aux - (aux * 0.01))
                    if aux <= stop:
                        print('Sair da posição')
                        leave_position(symbol) 
                else:    
                    print('Valor puro:',dayResult if dayResult <= 0 else dayResult - (dayResult * 0.01))
                    if dayResult <= stop:
                        print('Sair da posição')
                        leave_position(symbol) 
                print()
            
            if rastrear_media_movel:
                rates = format_rates(symbol,mt5.TIMEFRAME_M2,100)

                resultPositions = mt5.positions_get()
                if len(resultPositions) == 0:
                    status_order = None
                elif resultPositions[0].type == 0:
                    status_order = 'buy'
                elif resultPositions[0].type == 1:
                    status_order = 'sell'
                
                build_cross_avg_signal_list(symbol,status_order, rates, window=20)

    else:
        print('Error initializing  Metatrader')                

if __name__ == "__main__":
    main()