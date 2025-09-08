import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math
import pytz

def backtest_win(sma_period=21, angle_threshold=30, start_date=None, end_date=None):
    # Conectar ao MetaTrader 5
    if not mt5.initialize():
        print("Falha na inicialização do MT5")
        return
    
    # Configurar datas
    if start_date is None:
        start_date = datetime.now() - timedelta(days=30)
    if end_date is None:
        end_date = datetime.now()
    
    start_date = datetime(2025, 1, 1) # Data inicial
    end_date   = datetime(2025, 9, 8)

    # Obter dados do ativo WIN
    timeframe = mt5.TIMEFRAME_M5
    symbol = "WIN$"  # Símbolo do mini índice

    timezone = pytz.timezone("America/Sao_Paulo")

            # Converter para UTC
    start_date = timezone.localize(start_date).astimezone(pytz.utc)
    end_date = timezone.localize(end_date).astimezone(pytz.utc)
    
    rates = mt5.copy_rates_range(symbol, timeframe, start_date, end_date)
    if rates is None:
        print("Nenhum dado obtido")
        mt5.shutdown()
        return
    
    # Converter para DataFrame
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Calcular SMA
    df['sma'] = df['close'].rolling(window=sma_period).mean()
    
    # Calcular ângulo da SMA (usando 5 barras para cálculo da inclinação)
    lookback = 5
    df['angle'] = 0.0
    
    for i in range(lookback, len(df)):
        # Calcular inclinação (pontos por barra)
        slope = (df['sma'].iloc[i] - df['sma'].iloc[i-lookback]) / lookback
        
        # Converter para graus
        angle_rad = math.atan(slope)
        angle_deg = math.degrees(angle_rad)
        df.at[df.index[i], 'angle'] = angle_deg
    
    # Inicializar variáveis do backtest
    initial_balance = 1000.0
    balance = initial_balance
    position = None  # None, 'buy', or 'sell'
    entry_price = 0.0
    operation_code = 0
    results = []
    
    # Simular operações
    for i in range(lookback, len(df)):
        current_bar = df.iloc[i]
        prev_bar = df.iloc[i-1] if i > 0 else None
        
        # Verificar condições de saída
        exit_trade = False
        
        # Regra 2: Encerrar às 18h
        if current_bar['time'].hour >= 18:
            exit_trade = True
        
        # Regra 1: Encerrar no final do dia
        if prev_bar is not None and current_bar['time'].date() != prev_bar['time'].date():
            exit_trade = True
        
        # Verificar saída por ângulo
        if position == 'buy' and current_bar['angle'] < angle_threshold:
            exit_trade = True
        elif position == 'sell' and current_bar['angle'] > -angle_threshold:
            exit_trade = True
        
        # Executar saída
        if position and exit_trade:
            # Calcular resultado
            if position == 'buy':
                result = (current_bar['close'] - entry_price) * 0.20
            else:
                result = (entry_price - current_bar['close']) * 0.20
            
            balance += result
            
            # Registrar saída
            results.append({
                'Código da operação': operation_code,
                'Data e hora': current_bar['time'],
                'Tipo': 'Saída',
                'Lado': position,
                'Preço': current_bar['close'],
                'Resultado': result,
                'Saldo': balance
            })
            
            position = None
        
        # Verificar condições de entrada
        if not position:
            if current_bar['angle'] > angle_threshold:
                position = 'buy'
                entry_price = current_bar['close']
                operation_code += 1
                
                # Registrar entrada
                results.append({
                    'Código da operação': operation_code,
                    'Data e hora': current_bar['time'],
                    'Tipo': 'Entrada',
                    'Lado': 'Compra',
                    'Preço': entry_price,
                    'Resultado': 0.0,
                    'Saldo': balance
                })
                
            elif current_bar['angle'] < -angle_threshold:
                position = 'sell'
                entry_price = current_bar['close']
                operation_code += 1
                
                # Registrar entrada
                results.append({
                    'Código da operação': operation_code,
                    'Data e hora': current_bar['time'],
                    'Tipo': 'Entrada',
                    'Lado': 'Venda',
                    'Preço': entry_price,
                    'Resultado': 0.0,
                    'Saldo': balance
                })
    
    # Criar DataFrame com resultados
    results_df = pd.DataFrame(results)
    
    # Salvar em CSV
    filename = f"backtest_win_sma{sma_period}_angle{angle_threshold}.csv"
    results_df.to_csv(filename, index=False, decimal=',')
    
    # Exibir resultados
    print(f"Backtest concluído! Saldo final: R$ {balance:.2f}")
    print(f"Arquivo salvo: {filename}")
    print(f"Total de operações: {operation_code}")
    
    # Desconectar do MT5
    mt5.shutdown()

# Exemplo de uso
if __name__ == "__main__":
    # Parâmetros configuráveis
    sma_period = 21      # Período da SMA
    angle_threshold = 30 # Ângulo limite em graus
    start_date = datetime(2023, 1, 1)  # Data inicial
    end_date = datetime(2023, 12, 31)   # Data final
    
    # Executar backtest
    backtest_win(
        sma_period=sma_period,
        angle_threshold=angle_threshold,
        start_date=start_date,
        end_date=end_date
    )