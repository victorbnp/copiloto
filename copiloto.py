import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz
import time
import os

# Função para limpar o console
def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

# Função para calcular o maior múltiplo de 3
def maior_multiplo_de_3_ate(quantidade):
    return (quantidade // 3) * 3

# Inicializar o MT5
if not mt5.initialize():
    print("❌ Falha ao inicializar o MT5")
    quit()

print("✅ MT5 inicializado com sucesso")

# Definir símbolo
symbol = "WINM25"

# Verificar se o símbolo existe
symbol_info = mt5.symbol_info(symbol)
if symbol_info is None:
    print(f"❌ Símbolo '{symbol}' não encontrado no MT5.")
    quit()

print(f"✅ Símbolo '{symbol}' encontrado.")

# === CONFIGURAÇÕES DO USUÁRIO ===
risco_maximo_reais = 100.0  # R$ 100,00 por operação
valor_por_ponto = 0.20      # WINM25 = R$ 0,50 por ponto

# Loop contínuo
try:
    while True:
        clear_console()

        timezone = pytz.timezone('America/Sao_Paulo')
        date1 = datetime(datetime.now().year, datetime.now().month, datetime.now().day,tzinfo=timezone)

        # Pegar últimos N ticks
        N_TICKS = 10000000  # Ajuste conforme necessário
        ticks = mt5.copy_ticks_from(symbol, date1, N_TICKS, mt5.COPY_TICKS_ALL)

        if ticks is None or len(ticks) == 0:
            print("❌ Sem ticks retornados.")
        else:
            df_ticks = pd.DataFrame(ticks)
            df_ticks['time'] = pd.to_datetime(df_ticks['time'], unit='s')
            df_ticks.set_index('time', inplace=True)

            # Resample por 30 segundos usando 'last' para bid/ask
            df_30s = df_ticks['bid'].resample('30s').agg(['first', 'max', 'min', 'last'])
            df_30s.columns = ['open', 'high', 'low', 'close']
            df_30s.reset_index(inplace=True)

            print("\n🕰️ Candles reais de 30 segundos (construídos a partir de ticks):")
            print(df_30s.tail(10))

            # === ADICIONADO: Cálculo de risco e quantidade de contratos ===
            print("\n\n💰 Comparativo: Contratos permitidos x Contratos múltiplos de 3:")

            # Pegar preço atual (último bid disponível)
            preco_atual = df_ticks['bid'].iloc[-1]
            print(f"\n🎯 Preço atual (último bid): {preco_atual:.2f}")

            for n in [1, 2, 3]:
                if len(df_30s) < n:
                    print(f"\n⚠️ Não há {n} barras disponíveis para cálculo.")
                    continue

                ultimas_barras = df_30s.tail(n)

                # Calcular low e high nas últimas N barras
                lowest_low = ultimas_barras['low'].min()
                highest_high = ultimas_barras['high'].max()

                # Risco para COMPRA: diferença entre PREÇO ATUAL e LOW mais baixo
                risco_compra_pontos = preco_atual - lowest_low
                risco_compra_reais = abs(risco_compra_pontos) * valor_por_ponto

                # Risco para VENDA: diferença entre PREÇO ATUAL e HIGH mais alto
                risco_venda_pontos = highest_high - preco_atual
                risco_venda_reais = abs(risco_venda_pontos) * valor_por_ponto

                # Quantidade de contratos
                qtd_compra = int(risco_maximo_reais // risco_compra_reais) if risco_compra_reais > 0 else 0
                qtd_venda = int(risco_maximo_reais // risco_venda_reais) if risco_venda_reais > 0 else 0

                # Aplicar restrição de múltiplo de 3
                qtd_compra_valida = maior_multiplo_de_3_ate(qtd_compra)
                qtd_venda_valida = maior_multiplo_de_3_ate(qtd_venda)

                print(f"\n📊 Últimas {n} barra(s):")
                print(f"🔹 Low mais baixo: {lowest_low:.2f}")
                print(f"🔹 High mais alto: {highest_high:.2f}")
                print(f"🟢 Compra → {qtd_compra:2d} contrato(s)   ➡️ ✅ Usar: {qtd_compra_valida}")
                print(f"🔴 Venda → {qtd_venda:2d} contrato(s)   ➡️ ✅ Usar: {qtd_venda_valida}")

        # Aguardar 1 segundo antes da próxima atualização
        time.sleep(3)

except KeyboardInterrupt:
    print("\n🛑 Programa interrompido pelo usuário.")
finally:
    mt5.shutdown()