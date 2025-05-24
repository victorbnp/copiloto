
from datetime import datetime, timedelta
import MetaTrader5 as mt5
from random import randrange
import time
import pandas as pd
import numpy as np

# Função para encontrar suportes (fundos) e resistências (topos) relevantes
def find_support_resistance(prices, min_distance=10, min_amplitude=0.05):
    """
    Função para encontrar suportes e resistências relevantes baseando-se em distância mínima e amplitude de preço.
    :param prices: Série de preços (fechamento).
    :param min_distance: Distância mínima entre dois topos/fundos (em número de candles).
    :param min_amplitude: Variação percentual mínima entre topos e fundos consecutivos.
    :return: Índices de suportes (fundos) e resistências (topos) relevantes.
    """
    peaks = []
    bottoms = []
    
    for i in range(min_distance, len(prices) - min_distance):
        # Verifica se o preço atual é maior que os 'min_distance' anteriores e próximos (resistência - topo)
        if prices[i] == max(prices[i-min_distance:i+min_distance]):
            if len(peaks) == 0 or abs(prices[i] - prices[peaks[-1]]) / prices[peaks[-1]] >= min_amplitude:
                peaks.append(i)
        
        # Verifica se o preço atual é menor que os 'min_distance' anteriores e próximos (suporte - fundo)
        elif prices[i] == min(prices[i-min_distance:i+min_distance]):
            if len(bottoms) == 0 or abs(prices[i] - prices[bottoms[-1]]) / prices[bottoms[-1]] >= min_amplitude:
                bottoms.append(i)

    return peaks, bottoms

# Função principal para verificar se o preço está próximo de um suporte ou resistência relevante
def is_near_support_resistance(symbol, threshold=0.01, days=200, min_distance=10, min_amplitude=0.05):
    """
    Verifica se o preço de uma ação está próximo de um suporte ou resistência relevante.
    :param symbol: Símbolo da ação (e.g. "PETR4")
    :param threshold: Percentual de proximidade em relação ao suporte/resistência
    :param days: Quantidade de dias históricos para analisar
    :param min_distance: Distância mínima entre dois topos/fundos
    :param min_amplitude: Variação mínima de preço para considerar o suporte/resistência como relevante
    :return: Retorna True se o preço estiver próximo de um suporte ou resistência
    """
    
    # Obtendo os dados históricos diários
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, days)
    
    if rates is None:
        print(f"Falha ao obter dados para {symbol}")
        return None
    
    # Convertendo para DataFrame
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Identificando suportes e resistências relevantes
    peaks, bottoms = find_support_resistance(df['close'], min_distance, min_amplitude)
    
    # Obtendo o preço atual
    current_price = df['close'].iloc[-1]
    
    # Filtrando os preços dos topos (resistências) e fundos (suportes) relevantes
    resistance_prices = df['close'].iloc[peaks]
    support_prices = df['close'].iloc[bottoms]
    
    # Verificando se o preço está próximo de uma resistência ou suporte relevante
    near_resistance = any(abs(current_price - res) / current_price < threshold for res in resistance_prices)
    near_support = any(abs(current_price - sup) / current_price < threshold for sup in support_prices)
    
    return near_support, near_resistance

def verifica_candle_proximidade(symbol, timeframe, candles, limiar_percentual=10):
   # Solicita os dados de candles
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, candles)

    # Lista para armazenar os resultados
    resultados = []

    for rate in rates:
        abertura = rate['open']
        fechamento = rate['close']
        minima = rate['low']
        maxima = rate['high']

        # Determina se é um candle de alta ou de baixa
        if fechamento < abertura:  # Candle de baixa
            # Verifica proximidade do fechamento com a mínima
            proximidade_minima = ((fechamento - minima) / (maxima - minima)) * 100
            if proximidade_minima <= limiar_percentual:
                return True
        elif fechamento > abertura:  # Candle de alta
            # Verifica proximidade do fechamento com a máxima
            proximidade_maxima = ((maxima - fechamento) / (maxima - minima)) * 100
            if proximidade_maxima <= limiar_percentual:
                return True

    return False

def acoes_com_volume_muito_alto(acao, multiplicador=2):
    """
    Função que retorna as ações que tiveram um volume muito alto no último dia
    comparado com a média dos 8 dias anteriores.

    :param lista_acoes: Lista de símbolos de ações para verificar.
    :param multiplicador: Fator pelo qual o volume do último dia deve ser maior que a média dos últimos 8 dias.
    :return: Lista de ações com volume muito alto no último dia.
    """
 
    # Obter os dados históricos dos últimos 9 dias (timeframe diário)
    dados = mt5.copy_rates_from(acao, mt5.TIMEFRAME_D1, datetime.now(), 9)
    
    df_dados = pd.DataFrame(dados)
    
    # Calcular a média de volume dos últimos 8 dias (ignorando o último)
    media_volume_8_dias = df_dados['tick_volume'][:-1].mean()

    # Obter o volume do último dia
    volume_ultimo_dia = df_dados['tick_volume'].iloc[-1]

    # Comparar o volume do último dia com a média dos 8 dias anteriores
    if volume_ultimo_dia > media_volume_8_dias * multiplicador:
        return True
    

    return False


def calcular_risco_medio_reais(ativo, dias=8, lote=100):

    # Armazena o risco total em reais e a contagem de candles
    total_risco_reais = 0
    total_candles = 0
    
    # Loop pelos últimos 8 dias
    for dia in range(dias):
        # Define o início e o fim do período (das 10h às 12h) para o dia em questão
        hoje = datetime.now() - timedelta(days=dia)
        inicio = hoje.replace(hour=10, minute=0, second=0, microsecond=0)
        fim = hoje.replace(hour=12, minute=0, second=0, microsecond=0)
        
        # Obtém os candles de 2 minutos no intervalo de tempo especificado
        rates = mt5.copy_rates_range(ativo, mt5.TIMEFRAME_M2, inicio, fim)
        
        # Verifica se os dados foram retornados corretamente
        # if rates is None or len(rates) == 0:
        #     print(f"Falha ao obter dados de candles para {ativo} no dia {inicio.date()}")
        #     continue
        
        # Converte para DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Calcula o risco de cada candle em reais (diferença entre máximo e mínimo vezes o tamanho do lote)
        df['risco_reais'] = (df['high'] - df['low']) * lote
        
        # Soma o risco total em reais e conta o número de candles
        total_risco_reais += df['risco_reais'].sum()
        total_candles += len(df)
    
    # Calcula o risco médio em reais
    if total_candles == 0:
        print("Nenhum candle encontrado no período especificado.")
        return None
    
    risco_medio_reais = total_risco_reais / total_candles
    return risco_medio_reais

def verifica_volume_dobro(symbol, num_candles=10):
    # Obtém os dados dos últimos 11 candles (10 anteriores + o último)
    candles = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, num_candles + 1)
    candles = candles[:-1]
    # Verifica se foi possível obter os candles
    if candles is None or len(candles) < num_candles + 1:
        return False
    
    # Calcula a média do volume dos últimos 10 candles
    volumes = [candle['tick_volume'] for candle in candles[:-1]]  # Exclui o último candle
    media_volume = sum(volumes) / len(volumes)
    
    # Pega o volume do último candle
    ultimo_volume = candles[-1]['tick_volume']
    
    # Verifica se o volume do último candle é o dobro ou mais da média
    return ultimo_volume >= (media_volume)

def main():
    status_order = None
    
    ######################parâmetros######################
    abriu = False
    #######################################################

    if mt5.initialize():
       # Criando a lista
        acoes = [
            'CSAN3', 'MGLU3', 'BBAS3', 'JBSS3', 'LREN3', 'NTCO3', 'RAIL3', 
            'RDOR3', 'TIMS3', 'BBDC4', 'BBSE3', 'BRFS3', 'ELET3', 'ENEV3', 'ITUB4', 'MULT3', 'PRIO3', 
            'RENT3', 'SBSP3', 'SUZB3', 'UGPA3', 'VALE3', 'VIVT3', 'WEGE3', 'CYRE3', 'EMBR3', 'HYPE3', 'PETR3', 
            'PETR4', 'BRAV3', 'RADL3', 'ITSA4', 'ASAI3', 'AZUL4', 'ALOS3', 'AZZA3', 'BBDC3', 
            'CCRO3', 'MRVE3', 'TOTS3', 'USIM5', 'VIVA3', 'CRFB3', 'MRFG3', 
            'TRPL4', 'BRKM5', 'CURY3',  
            'EGIE3', 'IRBR3', 'POMO4', 'PSSA3', 'SLCE3', 
            'SMFT3', 'YDUQ3', 'BHIA3', 'CEAB3', 'CSMG3', 'DXCO3', 
            'ECOR3', 'EZTC3', 'ONCO3',
            'RECV3', 'SBFG3', 'TEND3'
        ]

        # Utilizando um laço para percorrer a lista e imprimir cada código
        print()
        for acao in acoes:
            rates = mt5.copy_rates_from(acao, mt5.TIMEFRAME_D1, datetime.now(), 4)
            if abriu:
                rates = mt5.copy_rates_from(acao, mt5.TIMEFRAME_D1, datetime.now(), 5)
            if rates is None or len(rates) < 3:
                print(f"Falha ao obter dados de candles para {acao}")
                continue
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')

            if abriu:
                
                # Verifica se os três últimos candles são positivos (fechamento > abertura)
                candle1_pos = df.iloc[-2]['close'] > df.iloc[-2]['open']
                candle2_pos = df.iloc[-3]['close'] > df.iloc[-3]['open']
                candle3_pos = df.iloc[-4]['close'] > df.iloc[-4]['open']
                candle4_pos = df.iloc[-5]['close'] > df.iloc[-5]['open']
            else:                
                candle1_pos = df.iloc[-1]['close'] > df.iloc[-1]['open']
                candle2_pos = df.iloc[-2]['close'] > df.iloc[-2]['open']
                candle3_pos = df.iloc[-3]['close'] > df.iloc[-3]['open']
                candle4_pos = df.iloc[-4]['close'] > df.iloc[-4]['open']
            
            # if ((not candle4_pos and candle3_pos and candle2_pos and candle1_pos) or (candle4_pos and not candle3_pos and not candle2_pos and not candle1_pos)) :
            #     #risco_medio = calcular_risco_medio_reais(acao, 8, 100)
            #     print(acao)
            # if ((not candle3_pos and candle2_pos and candle1_pos) or (candle3_pos and not candle2_pos and not candle1_pos)) :
            # #     risco_medio = calcular_risco_medio_reais(acao, 8, 100)
            #     print(acao)

            # acima da média
            candles_media = mt5.copy_rates_from_pos(acao, mt5.TIMEFRAME_D1, 0, 5)
            # Converte os dados para um DataFrame para facilitar a manipulação
            df_media = pd.DataFrame(candles_media)
            if abriu:
                candles_media = mt5.copy_rates_from_pos(acao, mt5.TIMEFRAME_D1, 0, 8)
                # Converte os dados para um DataFrame para facilitar a manipulação
                df_media = pd.DataFrame(candles_media)
                df_media = df_media.iloc[:-3]
            # Calcula o corpo de cada candle (diferença entre abertura e fechamento)
            df_media['corpo'] = abs(df_media['close'] - df_media['open'])
            
            # Obtém o corpo do último candle (primeira posição no DataFrame)
            corpo_ultimo_candle = df_media['corpo'].iloc[-1]

            # Calcula a média do corpo dos últimos 10 candles
            df_media = df_media.iloc[:-1]
            media_corpo = df_media['corpo'].mean()
            media_corpo = media_corpo * 2.5
            

            # Verifica se o corpo do último candle é maior que a média
            # resultado = corpo_ultimo_candle > media_corpo 
            # if (resultado):
            #     print(acao)


            #dobro volume
            # if verifica_volume_dobro(acao):
            #     print(acao)

            # acoes_com_volume_alto = acoes_com_volume_muito_alto(acao, multiplicador=2)
            # if acoes_com_volume_alto:
            #     print(acao)
            # resultado = verifica_candle_proximidade(acao, mt5.TIMEFRAME_D1, 1)
            # if resultado:
            #     print(acao) 
            # 
            near_support, near_resistance = is_near_support_resistance(acao, threshold=0.01, days=200, min_distance=10, min_amplitude=0.05)

            if near_support: # or  near_resistance:      
                print(acao)      

    else:
        print('Error initializing  Metatrader')                

if __name__ == "__main__":
    main()