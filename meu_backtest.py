import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, time
import pytz

# Configurações
symbol = "WIN$"
timeframe = mt5.TIMEFRAME_M1  # Timeframe de 1 minuto
tolerancia_barra = 0.30  # tolerância para barras
tolerancia_max_min = 0.1 # tolerância para max min
lote = 1  # Tamanho do lote (ajuste conforme sua conta)
num_barras = 5000  # Número de barras para análise (1 min cada)

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
def sao_parecidos_barras(v1, v2, v3, tolerancia_barra):
    media = np.mean([v1, v2, v3])
    if media == 0:
        return False
    desvio_max = tolerancia_barra * media
    return (abs(v1 - media) <= desvio_max and 
            abs(v2 - media) <= desvio_max and 
            abs(v3 - media) <= desvio_max)

def sao_parecidos_min_max(v1, v2, v3, tolerancia_max_min):
    valores = sorted([v1,v2,v3])
    # Atribuir cada valor ordenado
    menor, meio, maior = valores

    # Calcular as diferenças
    dif_maior_meio = maior - meio
    dif_meio_menor = meio - menor
    media = np.mean([dif_maior_meio,dif_meio_menor])
    if media == 0:
        return False
    desvio_max = tolerancia_max_min * media
    return (abs(dif_maior_meio - media) <= desvio_max and 
            abs(dif_meio_menor - media) <= desvio_max)


for i in range(3, len(df) - 1):
    # Dados das últimas 3 barras
    h1, h2, h3 = df['high'].iloc[i-3], df['high'].iloc[i-2], df['high'].iloc[i-1]
    l1, l2, l3 = df['low'].iloc[i-3], df['low'].iloc[i-2], df['low'].iloc[i-1]
    a1, a2, a3 = df['amplitude'].iloc[i-3], df['amplitude'].iloc[i-2], df['amplitude'].iloc[i-1]
    
    if (sao_parecidos_min_max(l1,l2,l3,tolerancia_max_min) and
        ((l3 > l2 > l1))):
        print(df['time'].iloc[i])
        print('entrou')
   



# Desconectar do MT5
mt5.shutdown()