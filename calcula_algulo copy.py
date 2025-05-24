import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import math
from datetime import datetime, timedelta

# Configuração: nome do ativo, período da EMA e intervalo entre pontos (em minutos)
ativo = "WIN$"
periodo_ema = 9
intervalo_minutos = 3

# Conectar ao MetaTrader 5
if not mt5.initialize():
    print("Erro ao inicializar o MetaTrader 5")
    quit()

# Obter os dados de fechamento do ativo
dados = mt5.copy_rates_from(ativo, mt5.TIMEFRAME_M1, datetime.now() - timedelta(days=5), 500)
if dados is None:
    print("Erro ao obter dados")
    mt5.shutdown()
    quit()

# Criar DataFrame com os dados de fechamento
df = pd.DataFrame(dados)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)

# Calcular a média móvel exponencial (EMA)
df['EMA'] = df['close'].ewm(span=periodo_ema, adjust=False).mean()

# Função para calcular o ângulo entre dois pontos da EMA
def calcular_angulo(ema1, ema2):
    delta_y = ema2 - ema1
    delta_x = intervalo_minutos  # Intervalo em minutos entre os pontos
    angulo_radianos = math.atan(delta_y / delta_x)
    angulo_graus = math.degrees(angulo_radianos)
    return angulo_graus

# Calcular o ângulo entre os últimos dois pontos da EMA
ema1 = df['EMA'].iloc[-2]
ema2 = df['EMA'].iloc[-1]
angulo = calcular_angulo(ema1, ema2)

print(f"Última EMA: {ema2}")
print(f"Ângulo entre os últimos dois pontos da EMA: {angulo:.2f} graus")

# Desconectar do MetaTrader 5
mt5.shutdown()
