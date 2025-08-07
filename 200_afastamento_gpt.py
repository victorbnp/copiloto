import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, time

# ========== CONFIGURAÇÕES ==========
ativo = "WIN$"  # ajuste conforme o símbolo no seu MT5
x_range = [0.5, 1.0, 1.5]  # Afastamento percentual para teste
data_inicio = datetime(2021, 1, 1)
data_fim = datetime(2024, 9, 30)
timeframe = mt5.TIMEFRAME_M1
saida_diaria = time(18, 0)
valor_por_ponto = 0.20  # R$ 0,20 por ponto
saldo_inicial = 1000.00  # R$ inicial
# ===================================

# Inicia conexão com MT5
if not mt5.initialize():
    raise RuntimeError("Erro ao conectar ao MetaTrader 5")

# Função para carregar dados históricos
def carregar_dados():
    #dados = mt5.copy_rates_range(ativo, timeframe, data_inicio, data_fim)
    dados = mt5.copy_rates_from_pos(ativo, timeframe, 0, 60000)
    df = pd.DataFrame(dados)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

# Função principal de backtest
def backtest(afastamento_percentual):
    df = carregar_dados()
    df['media_200'] = df['close'].rolling(200).mean()

    operacoes = []
    posicao = None
    codigo_op = 0

    for i in range(200, len(df)):
        row = df.iloc[i]
        preco = row['close']
        media = row['media_200']
        hora = row.name.time()

        if posicao and row.name.date() != posicao['data'].date():
            operacoes.append({
                'codigo': posicao['codigo'],
                'datetime': row.name,
                'tipo': 'Saída',
                'lado': posicao['lado'],
                'preco': preco
            })
            posicao = None
            continue

        if posicao and hora >= saida_diaria:
            operacoes.append({
                'codigo': posicao['codigo'],
                'datetime': row.name,
                'tipo': 'Saída',
                'lado': posicao['lado'],
                'preco': preco
            })
            posicao = None
            continue

        if not posicao:
            afastamento = ((preco - media) / media) * 100
            if afastamento >= afastamento_percentual:
                codigo_op += 1
                posicao = {
                    'codigo': codigo_op,
                    'data': row.name,
                    'lado': 'Venda'
                }
                operacoes.append({
                    'codigo': codigo_op,
                    'datetime': row.name,
                    'tipo': 'Entrada',
                    'lado': 'Venda',
                    'preco': preco
                })

            elif afastamento <= -afastamento_percentual:
                codigo_op += 1
                posicao = {
                    'codigo': codigo_op,
                    'data': row.name,
                    'lado': 'Compra'
                }
                operacoes.append({
                    'codigo': codigo_op,
                    'datetime': row.name,
                    'tipo': 'Entrada',
                    'lado': 'Compra',
                    'preco': preco
                })

        elif posicao:
            if (posicao['lado'] == 'Compra' and preco >= media) or \
               (posicao['lado'] == 'Venda' and preco <= media):
                operacoes.append({
                    'codigo': posicao['codigo'],
                    'datetime': row.name,
                    'tipo': 'Saída',
                    'lado': posicao['lado'],
                    'preco': preco
                })
                posicao = None

    return pd.DataFrame(operacoes)

# Executa para cada valor de afastamento
for x in x_range:
    print(f"\nRodando backtest para afastamento de {x}%...")
    resultado = backtest(x)

    resultado['resultado_op'] = None
    resultado['saldo'] = None
    saldo = saldo_inicial

    for codigo in resultado['codigo'].unique():
        entrada = resultado[(resultado['codigo'] == codigo) & (resultado['tipo'] == 'Entrada')]
        saida = resultado[(resultado['codigo'] == codigo) & (resultado['tipo'] == 'Saída')]

        if len(entrada) == 1 and len(saida) == 1:
            entrada = entrada.iloc[0]
            saida = saida.iloc[0]

            if entrada['lado'] == 'Compra':
                pontos = saida['preco'] - entrada['preco']
            elif entrada['lado'] == 'Venda':
                pontos = entrada['preco'] - saida['preco']
            else:
                pontos = 0

            lucro = pontos * valor_por_ponto
            saldo += lucro

            # Atualiza resultado da operação e saldo acumulado
            resultado.loc[
                (resultado['codigo'] == codigo) & (resultado['tipo'] == 'Saída'),
                ['resultado_op', 'saldo']
            ] = [lucro, saldo]

            resultado.loc[
                (resultado['codigo'] == codigo) & (resultado['tipo'] == 'Entrada'),
                'saldo'
            ] = saldo - lucro  # Saldo antes do lucro ser adicionado

    print(f"Saldo final para afastamento {x}%: R$ {saldo:.2f}")

    # Exporta CSV
    nome_arquivo = f"backtest_WIN_afastamento_{x:.1f}.csv"
    resultado[['codigo', 'datetime', 'tipo', 'lado', 'preco', 'resultado_op', 'saldo']].to_csv(nome_arquivo, index=False, sep=';')
    print(f"Arquivo salvo: {nome_arquivo}")

# Encerra conexão com MT5
mt5.shutdown()
