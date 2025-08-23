import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, time

# =============================
# CONFIGURAÇÕES DO SISTEMA
# =============================
SIMBOL = "WIN$"  # Mini Índice no MT5
PONTOS_POR_TICK = 5  # O preço muda em múltiplos de 5 pontos
VALOR_POR_PONTO = 0.20  # R$ 0,20 por ponto
VALOR_POR_TICK = PONTOS_POR_TICK * VALOR_POR_PONTO  # R$ 1,00 por tick
SALDO_INICIAL = 5000.0
HORA_FECHAMENTO = time(18, 0)  # 18:00

# Parâmetros a testar (alta do dia anterior > X%)
PERCENTUAIS_TESTE = [1.0, 1.2, 1.5]  # em %

# Período de teste
DATA_INICIAL = datetime(2024, 1, 1)
DATA_FINAL = datetime(2024, 10, 31)

# =============================
# INICIALIZAR MT5
# =============================
if not mt5.initialize():
    print("Falha ao inicializar MT5")
    quit()

print("MT5 inicializado com sucesso")

# =============================
# FUNÇÃO PARA BUSCAR DADOS
# =============================
def obter_dados(simbolo, data_ini, data_fim):
    rates = mt5.copy_rates_range(simbolo, mt5.TIMEFRAME_M1, data_ini, data_fim)
    if rates is None or len(rates) == 0:
        raise Exception(f"Sem dados para {simbolo} no período.")
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    # Resample para 1 minuto (já está, mas garantir)
    return df

# =============================
# FUNÇÃO DE BACKTEST
# =============================
def backtest_win(simbolo, data_ini, data_fim, perc_teste):
    print(f"\nIniciando backtest para {perc_teste}%...")
    
    # Obter dados de 1 minuto
    df_raw = obter_dados(simbolo, data_ini, data_fim)
    
    # Extrair dados diários para calcular a alta do dia anterior
    df_daily = df_raw.resample('D').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()
    df_daily = df_daily[(df_daily.index >= data_ini.date()) & (df_daily.index <= data_fim.date())]
    
    # Calcular variação percentual diária
    df_daily['daily_return'] = ((df_daily['close'] - df_daily['open']) / df_daily['open']) * 100
    df_daily['high_return'] = ((df_daily['high'] - df_daily['open']) / df_daily['open']) * 100
    df_daily['prev_high_return'] = df_daily['high_return'].shift(1)  # Alta do dia anterior
    
    # Mapear cada minuto para o dia correspondente
    df_raw['date'] = df_raw.index.date
    df_raw['time_only'] = df_raw.index.time
    
    # Dicionário para mapear dia -> alta do dia anterior
    prev_high_dict = df_daily['prev_high_return'].to_dict()
    
    # Listas para armazenar operações
    operacoes = []
    saldo = SALDO_INICIAL
    operacao_aberta = None
    codigo_op = 1
    
    # Iterar minuto a minuto
    for idx, row in df_raw.iterrows():
        current_date = row['date']
        current_time = row['time_only']
        close_atual = row['close']
        
        # Verificar se é um novo dia (para fechar operações do dia anterior)
        if operacao_aberta and operacao_aberta['data_entrada'].date() != current_date:
            # Fechar operação por mudança de dia
            preco_saida = close_atual
            resultado = (operacao_aberta['preco_entrada'] - preco_saida) * VALOR_POR_TICK
            saldo += resultado
            operacoes.append({
                'Codigo': codigo_op,
                'Data_Hora': idx,
                'Tipo': 'saída',
                'Lado': 'venda',
                'Preco': preco_saida,
                'Resultado': resultado,
                'Saldo': saldo
            })
            operacao_aberta = None
        
        # Fechar operação às 18h
        if operacao_aberta and current_time >= HORA_FECHAMENTO:
            preco_saida = close_atual
            resultado = (operacao_aberta['preco_entrada'] - preco_saida) * VALOR_POR_TICK
            saldo += resultado
            operacoes.append({
                'Codigo': codigo_op,
                'Data_Hora': idx,
                'Tipo': 'saída',
                'Lado': 'venda',
                'Preco': preco_saida,
                'Resultado': resultado,
                'Saldo': saldo
            })
            operacao_aberta = None
            codigo_op += 1
        
        # Evitar entrada após 18h
        if current_time >= HORA_FECHAMENTO:
            continue
        
        # Verificar se é o primeiro minuto do dia
        if current_time == df_raw.loc[df_raw['date'] == current_date].index.time.min():
            # Obter a alta do dia anterior
            prev_high_ret = prev_high_dict.get(current_date - pd.Timedelta(days=1))
            if prev_high_ret is None or prev_high_ret <= perc_teste:
                continue  # Não atende ao critério de alta
            
            # Calcular ponto de entrada: -1/3 da alta do dia anterior a partir do fechamento do dia anterior
            prev_close = df_daily.loc[current_date - pd.Timedelta(days=1), 'close']
            entrada_pct = -prev_high_ret / 3.0
            preco_entrada = prev_close * (1 + entrada_pct / 100)
            
            # Calcular stop e alvo
            risco_pct = prev_high_ret / 3.0 / 100  # em decimal
            stop_preco = preco_entrada * (1 + risco_pct)  # stop acima (para venda)
            alvo_preco = preco_entrada * (1 - 2 * risco_pct)  # alvo abaixo (2x risco)
            
            # Ajustar para múltiplos de 5 pontos
            def ajustar_preco(p):
                return round(p / 5) * 5
            
            preco_entrada = ajustar_preco(preco_entrada)
            stop_preco = ajustar_preco(stop_preco)
            alvo_preco = ajustar_preco(alvo_preco)
            
            # Armazenar parâmetros da operação
            operacao_aberta = {
                'codigo': codigo_op,
                'data_entrada': idx,
                'preco_entrada': preco_entrada,
                'stop': stop_preco,
                'alvo': alvo_preco
            }
            
            # Registrar entrada
            operacoes.append({
                'Codigo': codigo_op,
                'Data_Hora': idx,
                'Tipo': 'entrada',
                'Lado': 'venda',
                'Preco': preco_entrada,
                'Resultado': 0.0,
                'Saldo': saldo
            })
        
        # Gerenciar operação aberta
        if operacao_aberta and operacao_aberta['data_entrada'].date() == current_date:
            preco_atual = close_atual
            
            # Checar stop
            if preco_atual >= operacao_aberta['stop']:
                resultado = (operacao_aberta['preco_entrada'] - operacao_aberta['stop']) * VALOR_POR_TICK
                saldo += resultado
                operacoes.append({
                    'Codigo': operacao_aberta['codigo'],
                    'Data_Hora': idx,
                    'Tipo': 'saída',
                    'Lado': 'venda',
                    'Preco': operacao_aberta['stop'],
                    'Resultado': resultado,
                    'Saldo': saldo
                })
                operacao_aberta = None
                codigo_op += 1
            
            # Checar alvo
            elif preco_atual <= operacao_aberta['alvo']:
                resultado = (operacao_aberta['preco_entrada'] - operacao_aberta['alvo']) * VALOR_POR_TICK
                saldo += resultado
                operacoes.append({
                    'Codigo': operacao_aberta['codigo'],
                    'Data_Hora': idx,
                    'Tipo': 'saída',
                    'Lado': 'venda',
                    'Preco': operacao_aberta['alvo'],
                    'Resultado': resultado,
                    'Saldo': saldo
                })
                operacao_aberta = None
                codigo_op += 1
    
    # Fechar operação pendente no final do período
    if operacao_aberta:
        preco_saida = df_raw.iloc[-1]['close']
        resultado = (operacao_aberta['preco_entrada'] - preco_saida) * VALOR_POR_TICK
        saldo += resultado
        operacoes.append({
            'Codigo': operacao_aberta['codigo'],
            'Data_Hora': df_raw.index[-1],
            'Tipo': 'saída',
            'Lado': 'venda',
            'Preco': preco_saida,
            'Resultado': resultado,
            'Saldo': saldo
        })
    
    # Criar DataFrame de operações
    df_resultado = pd.DataFrame(operacoes)
    if not df_resultado.empty:
        df_resultado = df_resultado.sort_values(['Codigo', 'Data_Hora'])
        df_resultado['Resultado'] = df_resultado['Resultado'].round(2)
        df_resultado['Saldo'] = df_resultado['Saldo'].round(2)
    
    return df_resultado, saldo

# =============================
# EXECUÇÃO PARA MÚLTIPLOS PARÂMETROS
# =============================
resultados_finais = []

for perc in PERCENTUAIS_TESTE:
    df_ops, saldo_final = backtest_win(SIMBOL, DATA_INICIAL, DATA_FINAL, perc)
    
    # Salvar CSV
    nome_arquivo = f"backtest_win_{int(perc*10)}.csv"
    if not df_ops.empty:
        df_ops.to_csv(nome_arquivo, index=False)
        total_ops = df_ops[df_ops['Tipo'] == 'saída'].shape[0]
        wins = df_ops[df_ops['Resultado'] > 0].shape[0]
        win_rate = (wins / total_ops * 100) if total_ops > 0 else 0
    else:
        total_ops = 0
        win_rate = 0
    
    resultados_finais.append({
        'Percentual': perc,
        'Saldo_Final': round(saldo_final, 2),
        'Operacoes': total_ops,
        'Win_Rate': round(win_rate, 2)
    })

# Mostrar resumo
print("\n" + "="*50)
print("RESUMO DOS TESTES")
print("="*50)
for res in resultados_finais:
    print(f"Alta > {res['Percentual']}%: Saldo Final = R$ {res['Saldo_Final']}, "
          f"Operações = {res['Operacoes']}, Win Rate = {res['Win_Rate']}%")

# Salvar resumo
pd.DataFrame(resultados_finais).to_csv("resumo_backtests.csv", index=False)

# Fechar MT5
mt5.shutdown()