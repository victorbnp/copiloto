import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, time
import pytz

# Configurações
symbol = "WIN$"
timeframe = mt5.TIMEFRAME_M2  # Timeframe de 1 minuto
tolerancia = 0.20  # 10% de tolerância para amplitudes/mínimas/máximas
lote = 1  # Tamanho do lote (ajuste conforme sua conta)
num_barras = 50000  # Número de barras para análise (1 min cada)

# Conectar ao MetaTrader 5
if not mt5.initialize():
    print("Falha ao inicializar MT5")
    mt5.shutdown()
    exit()

# Obter dados históricos
rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_barras)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df['amplitude'] = df['high'] - df['low']

# Filtro de horário (pregão B3: 10h às 18h BRT)
df['hora'] = df['time'].dt.tz_localize(pytz.utc).dt.tz_convert('America/Sao_Paulo').dt.time
df = df[(df['hora'] >= time(10, 0)) & (df['hora'] <= time(17, 55))]  # Evitar fechamento

# Função para verificar similaridade (10%)
def sao_parecidos(v1, v2, v3, tolerancia):
    media = np.mean([v1, v2, v3])
    if media == 0:
        return False
    desvio_max = tolerancia * media
    return (abs(v1 - media) <= desvio_max and 
            abs(v2 - media) <= desvio_max and 
            abs(v3 - media) <= desvio_max)

# Backtest
operacoes = []

for i in range(3, len(df) - 1):
    # Dados das últimas 3 barras
    h1, h2, h3 = df['high'].iloc[i-3], df['high'].iloc[i-2], df['high'].iloc[i-1]
    l1, l2, l3 = df['low'].iloc[i-3], df['low'].iloc[i-2], df['low'].iloc[i-1]
    a1, a2, a3 = df['amplitude'].iloc[i-3], df['amplitude'].iloc[i-2], df['amplitude'].iloc[i-1]
    
    # Verificar condições para COMPRA (mínimas e amplitudes parecidas)
    if (sao_parecidos(a1, a2, a3, tolerancia) and 
        sao_parecidos(l1, l2, l3, tolerancia) and
        (l3 > l2 > l1)):
        entrada = df['open'].iloc[i]  # Preço de entrada na abertura da barra atual
        stop_loss = l1  # Stop Loss abaixo da mínima da PRIMEIRA barra
        risco = entrada - stop_loss  # Cálculo do risco (distância entre entrada e SL)
        take_profit1 = entrada + risco  # TP1 = 1x risco
        take_profit2 = entrada + 2 * risco  # TP2 = 2x risco
        direcao = "COMPRA"
        
        operacoes.append({
            'time': df['time'].iloc[i],
            'direcao': direcao,
            'entrada': entrada,
            'stop_loss': stop_loss,
            'take_profit1': take_profit1,
            'take_profit2': take_profit2,
            'resultado': None
        })
    
    # Verificar condições para VENDA (máximas e amplitudes parecidas)
    elif (sao_parecidos(a1, a2, a3, tolerancia) and 
          sao_parecidos(h1, h2, h3, tolerancia) and
          (h3 < h2 < h1)):
        entrada = df['open'].iloc[i]
        stop_loss = h1  # Stop Loss acima da máxima da PRIMEIRA barra
        risco = stop_loss - entrada  # Cálculo do risco
        take_profit1 = entrada - 2 * risco  # TP1 = 1x risco
        take_profit2 = entrada - 3 * risco  # TP2 = 2x risco
        direcao = "VENDA"
        
        operacoes.append({
            'time': df['time'].iloc[i],
            'direcao': direcao,
            'entrada': entrada,
            'stop_loss': stop_loss,
            'take_profit1': take_profit1,
            'take_profit2': take_profit2,
            'resultado': None
        })

# Simular resultados das operações
for op in operacoes:
    idx = df[df['time'] >= op['time']].index[0]
    sub_df = df.loc[idx:]
    
    for _, row in sub_df.iterrows():
        # Verificar se atingiu Stop Loss ou Take Profit
        if op['direcao'] == "COMPRA":
            if row['low'] <= op['stop_loss']:
                op['resultado'] = -1  # Loss (1x risco)
                break
            elif row['high'] >= op['take_profit2']:
                op['resultado'] = 3  # Ganho 2x risco
                break
            elif row['high'] >= op['take_profit1']:
                op['resultado'] = 2  # Ganho 1x risco (parcial)
                break
        else:  # VENDA
            if row['high'] >= op['stop_loss']:
                op['resultado'] = -1  # Loss (1x risco)
                break
            elif row['low'] <= op['take_profit2']:
                op['resultado'] = 3  # Ganho 2x risco
                break
            elif row['low'] <= op['take_profit1']:
                op['resultado'] = 2  # Ganho 1x risco (parcial)
                break

# Estatísticas
df_operacoes = pd.DataFrame(operacoes)
if not df_operacoes.empty:
    win_rate = (len(df_operacoes[df_operacoes['resultado'] > 0]) / len(df_operacoes)) * 100
    profit_factor = (df_operacoes[df_operacoes['resultado'] > 0]['resultado'].sum() / 
                     abs(df_operacoes[df_operacoes['resultado'] < 0]['resultado'].sum()))
    print(f"Total de operações: {len(df_operacoes)}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Profit Factor: {profit_factor:.2f}")
else:
    print("Nenhuma operação encontrada.")

# Desconectar do MT5
mt5.shutdown()