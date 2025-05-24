import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox

# Função para inicializar a conexão com o MetaTrader 5
def inicializar_mt5():
    if not mt5.initialize():
        messagebox.showerror("Erro", "Falha ao inicializar o MT5")
        return False
    return True


def listar_acoes_day_trade(timeframe=mt5.TIMEFRAME_M2, volume_min=1000):
    """
    Lista as ações disponíveis para day trade no gráfico de 2 minutos.
    
    :param timeframe: O timeframe a ser analisado (padrão é 2 minutos).
    :param volume_min: O volume mínimo de negociação para ser considerado adequado para day trade.
    :return: Lista de ações que atendem aos critérios.
    """
    # Obtendo todos os símbolos do MetaTrader 5
    simbolos = mt5.symbols_get()
    
    # Lista para armazenar os ativos que são adequados para day trade
    acoes_day_trade = []

    # Intervalo de tempo (última hora para análise de volatilidade e volume)
    data_atual = datetime.now()
    data_inicio = data_atual - timedelta(hours=1)

    for simbolo in simbolos:
        # Ativar o símbolo para negociação
        if not simbolo.visible:
            mt5.symbol_select(simbolo.name, True)

        # Obter os dados históricos (última hora no gráfico de 2 minutos)
        dados = mt5.copy_rates_range(simbolo.name, timeframe, data_inicio, data_atual)
        
        if dados is None or len(dados) == 0:
            continue

        # Converter para DataFrame para facilitar a análise
        df_dados = pd.DataFrame(dados)

        # Verificar volume e volatilidade (variação de preço)
        volume_total = df_dados['tick_volume'].sum()
        volatilidade = df_dados['high'].max() - df_dados['low'].min()

        # Critérios para ser considerado um ativo de day trade
        if volume_total > volume_min and volatilidade > 0:
            acoes_day_trade.append(simbolo.name)
    
    return acoes_day_trade



# Executar a aplicação
if __name__ == "__main__":
    # Executando a função
    acoes_para_day_trade = listar_acoes_day_trade()

    # Mostrando os resultados
    print("Ações adequadas para day trade:", acoes_para_day_trade)
