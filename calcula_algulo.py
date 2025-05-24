import MetaTrader5 as mt5
import numpy as np
import math
import time

# Inicializando o MetaTrader 5
mt5.initialize()

while 1==1:
    # Definindo o ativo e o timeframe
    symbol = "WINZ24"
    timeframe = mt5.TIMEFRAME_M1  # 15 minutos, por exemplo
    periodo_ema = 4  # Defina o período da EMA
    periodo_ema2 = 9  # Defina o período da EMA

    # Obtendo os últimos 100 candles
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 100)
    # mt5.shutdown()

    # Extraindo os preços de fechamento
    fechamento = [rate['close'] for rate in rates]

    # Calculando a EMA usando uma função do numpy
    def calcular_ema(precos, periodo):
        return np.convolve(precos, np.ones((periodo,))/periodo, mode='valid')

    ema = calcular_ema(fechamento, periodo_ema)
    ema2 = calcular_ema(fechamento, periodo_ema2)

    # Selecionando os últimos 2 pontos da EMA para calcular a inclinação
    ponto_1 = ema[-3]
    ponto_2 = ema[-2]

    ponto_12 = ema2[-3]
    ponto_22 = ema2[-2]

    # Calculando a inclinação (diferença de preços) e a distância em tempo
    diferenca_precos = ponto_2 - ponto_1
    diferenca_tempo = 2  # Cada ponto de EMA representa um candle, então a diferença é de 1 unidade

    diferenca_precos2 = ponto_22 - ponto_12
    diferenca_tempo2 = 2  # Cada ponto de EMA representa um candle, então a diferença é de 1 unidade



    # Calculando o ângulo em radianos e depois em graus
    angulo_radianos = math.atan(diferenca_precos / diferenca_tempo)
    angulo_graus = math.degrees(angulo_radianos)

    angulo_radianos2 = math.atan(diferenca_precos2 / diferenca_tempo2)
    angulo_graus2 = math.degrees(angulo_radianos2)


    print(f"O ângulo da EMA é aproximadamente {angulo_graus:.2f} .,  {angulo_graus2:.2f} graus")
    #print(f"O ângulo da EMA2 é aproximadamente {angulo_graus2:.2f} graus")

    time.sleep(1)
