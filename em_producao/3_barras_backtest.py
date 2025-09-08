import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
# import matplotlib.pyplot as plt

# Inicializa conexão com MT5
if not mt5.initialize():
    print("Erro ao inicializar MT5")
    quit()

# Definir símbolo e timeframe
symbol = "WIN$"  # Certifique-se de que este símbolo está disponível no seu terminal MT5
timeframe = mt5.TIMEFRAME_M30  # Pode ser alterado para M5, M15, H1 etc.
n_bars = 50000  # Número de velas para carregar

# Carrega dados
rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_bars)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

# Colunas úteis
df['open'] = df['open']
df['high'] = df['high']
df['low'] = df['low']
df['close'] = df['close']

# Identifica se cada barra é up ou down
df['up_bar'] = df['close'] > df['open']
df['down_bar'] = df['close'] < df['open']

# Conta sequências de 3 barras consecutivas
df['up_count'] = df['up_bar'].rolling(window=3).sum() == 3
df['down_count'] = df['down_bar'].rolling(window=3).sum() == 3

# Inicialização do backtest
position = None  # 'long', 'short' ou None
entry_price = None
capital = 1000  # Capital inicial
lot_size = 0.2  # Tamanho do contrato (ex: 1 ponto = R$ 0.50 no mini índice)
results = []
data_posterior = None

for i in range(3, len(df)):
    time = df.iloc[i]['time']
    price = df.iloc[i]['close']

    data_posterior = None if ((i+1) > (len(df)-1)) else df.iloc[i+1]['time'].date()
    mudou_dia = False if not data_posterior else data_posterior != df.iloc[i]['time'].date()
    # Verifica se é 18h
    if ((time.hour == 18 and time.minute == 0) or (mudou_dia)):
        if position == 'long':
            profit = (price - entry_price) * lot_size
            capital += profit
            results.append((time, price, 'exit_long_eod', profit, capital))
            position = None
        elif position == 'short':
            profit = (entry_price - price) * lot_size
            capital += profit
            results.append((time, price, 'exit_short_eod', profit, capital))
            position = None
        continue  # Não entra em nova operação após fechar

    # Verificar condições de entrada/saída (somente se não fechou por EOD)
    if df.iloc[i]['up_count']:
        if position == 'short':
            # Fechar short
            profit = (entry_price - price) * lot_size
            capital += profit
            results.append((time, price, 'exit_short', profit, capital))
            position = None

        if position is None:
            # Entrar long
            entry_price = price
            position = 'long'
            results.append((time, price, 'enter_long', 0, capital))

    elif df.iloc[i]['down_count']:
        if position == 'long':
            # Fechar long
            profit = (price - entry_price) * lot_size
            capital += profit
            results.append((time, price, 'exit_long', profit, capital))
            position = None

        if position is None:
            # Entrar short
            entry_price = price
            position = 'short'
            results.append((time, price, 'enter_short', 0, capital))


# Exibir resultados
print(f"\nCapital final: R$ {capital:.2f}")

# Transformar resultados em DataFrame
trades_df = pd.DataFrame(results, columns=['time', 'price', 'action', 'profit', 'capital'])
print("\nHistórico de trades:")
print(trades_df)

# Plotar evolução do capital
# plt.plot(trades_df['time'], trades_df['capital'])
# plt.title('Evolução do Capital')
# plt.xlabel('Tempo')
# plt.ylabel('Capital (R$)')
# plt.grid(True)
# plt.show()