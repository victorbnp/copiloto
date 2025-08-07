import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, time
import pytz

# Configurações
symbol = "WIN$N"
timeframe = mt5.TIMEFRAME_M1
tolerancia = 0.10  # 10%
lote = 1
num_barras = 50000

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
df = df[(df['hora'] >= time(10, 0)) & (df['hora'] <= time(17, 55))]

# Calcular média móvel de 20 períodos
df['mm20'] = df['close'].rolling(window=20).mean()

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
    h1, h2, h3 = df['high'].iloc[i-3], df['high'].iloc[i-2], df['high'].iloc[i-1]
    l1, l2, l3 = df['low'].iloc[i-3], df['low'].iloc[i-2], df['low'].iloc[i-1]
    a1, a2, a3 = df['amplitude'].iloc[i-3], df['amplitude'].iloc[i-2], df['amplitude'].iloc[i-1]
    
    # Condições para COMPRA
    if (sao_parecidos(a1, a2, a3, tolerancia) and 
        sao_parecidos(l1, l2, l3, tolerancia) and 
        (l3 > l2 > l1)):
        entrada = df['open'].iloc[i]
        stop_loss = l1
        risco = entrada - stop_loss
        take_profit1 = entrada + risco
        take_profit2 = entrada + 2 * risco
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
    
    # Condições para VENDA
    elif (sao_parecidos(a1, a2, a3, tolerancia) and 
          sao_parecidos(h1, h2, h3, tolerancia) and 
          (h3 < h2 < h1)):
        entrada = df['open'].iloc[i]
        stop_loss = h1
        risco = stop_loss - entrada
        take_profit1 = entrada - risco
        take_profit2 = entrada - 2 * risco
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

# Simulação das operações
for op in operacoes:
    idx = df[df['time'] >= op['time']].index[0]
    sub_df = df.loc[idx:]
    parcial_atingida = False
    
    for _, row in sub_df.iterrows():
        if op['direcao'] == "COMPRA":
            if row['low'] <= op['stop_loss']:
                op['resultado'] = -1
                break
            elif not parcial_atingida and row['high'] >= op['take_profit1']:
                parcial_atingida = True
                op['stop_loss'] = op['entrada']
            elif parcial_atingida and row['high'] >= op['take_profit2'] and row['close'] > row['mm20']:
                op['resultado'] = 2
                break
        else:  # VENDA
            if row['high'] >= op['stop_loss']:
                op['resultado'] = -1
                break
            elif not parcial_atingida and row['low'] <= op['take_profit1']:
                parcial_atingida = True
                op['stop_loss'] = op['entrada']
            elif parcial_atingida and row['low'] <= op['take_profit2'] and row['close'] < row['mm20']:
                op['resultado'] = 2
                break
    
    if parcial_atingida and op['resultado'] is None:
        op['resultado'] = 1

# Cálculo das estatísticas
ganho_total = 0
perda_total = 0

for op in operacoes:
    if op['resultado'] > 0:
        ganho_total += op['resultado']
    else:
        perda_total += abs(op['resultado'])

profit_factor = ganho_total / perda_total if perda_total != 0 else float('inf')
win_rate = (len([op for op in operacoes if op['resultado'] > 0]) / len(operacoes)) * 100

print("\n--- RESULTADOS ---")
print(f"Total de operações: {len(operacoes)}")
print(f"Win Rate: {win_rate:.2f}%")
print(f"Profit Factor: {profit_factor:.2f}")
print("------------------")

# Desconectar do MT5
mt5.shutdown()