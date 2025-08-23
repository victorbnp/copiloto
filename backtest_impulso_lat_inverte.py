import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import csv
import pytz

# Inicializa MT5
if not mt5.initialize():
    print("Erro ao inicializar MT5")
    quit()

# Configurações
symbol = "WIN$"  # Mini Ibovespa no MT5
timeframe = mt5.TIMEFRAME_M5  # 1 minuto
initial_balance = 1000.0
start_date = datetime(2025, 1, 1)  # Altere conforme necessário
end_date = datetime(2025, 8, 14)  # Altere conforme necessário

# Parâmetros do sistema
entry_hour = 9  # Apenas entradas após 14h
exit_hour = 18   # Saída até 18h
contract_size = 1  # 1 contrato
tick_value = 1.0  # Cada tick = R$1,00 (5 pontos = R$0,20 → cada tick é 5 pontos)

# Função para obter dados históricos
def get_data(symbol, timeframe, start, end):

    timezone = pytz.timezone("America/Sao_Paulo")

    start = timezone.localize(start).astimezone(pytz.utc)
    end = timezone.localize(end).astimezone(pytz.utc)

    rates = mt5.copy_rates_range(symbol, timeframe, start, end)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

# Carregar dados
print("Carregando dados...")
data = get_data(symbol, timeframe, start_date, end_date)

# Preparar colunas úteis
data['hour'] = data.index.hour
data['minute'] = data.index.minute
data['date'] = data.index.date
data['open_price'] = data['open']
data['high_price'] = data['high']
data['low_price'] = data['low']
data['close_price'] = data['close']

# Variáveis de controle
trades = []
current_trade = None
trade_id_counter = 0
balance = initial_balance
profit = 0

# Lógica de negociação
for i in range(1, len(data)):
    row = data.iloc[i]
    prev_row = data.iloc[i-1]

    # Verificar se é possível entrar (após 14h)
    if row['hour'] >= entry_hour and row['hour'] < exit_hour:
        # Verifica se há tendência de alta anterior
        high_prev_3 = data['high_price'].iloc[max(0, i-3):i].max()
        low_prev_3 = data['low_price'].iloc[max(0, i-3):i].min()
        # Tendência de alta: alto subindo e baixo subindo
        if (prev_row['close_price'] > prev_row['open_price'] and
            prev_row['close_price'] > prev_row['open_price'] * 1.01 and
            prev_row['high_price'] > high_prev_3 and
            prev_row['low_price'] > low_prev_3):
            
            # Consolidação lateral: preço oscilando em um pequeno range
            # Considerar os últimos 5 candles como consolidação
            recent_high = data['high_price'].iloc[max(0, i-5):i].max()
            recent_low = data['low_price'].iloc[max(0, i-5):i].min()
            range_consolidation = recent_high - recent_low
            avg_price = (recent_high + recent_low) / 2
            
            # Barra forte de baixa: corpo longo para baixo
            body_size = abs(row['close_price'] - row['open_price'])
            if (row['close_price'] < row['open_price'] and
                body_size > 0.0002 and  # ajuste conforme volatilidade
                row['low_price'] < row['open_price'] * 0.98 and
                row['low_price'] < avg_price):
                
                # Entrada em venda
                trade_id = f"TRADE_{trade_id_counter}"
                entry_time = row.name
                entry_price = row['close_price']
                trade_type = 'entrada'
                side = 'venda'
                result = 0
                balance -= contract_size * tick_value  # custo de entrada (simulado)
                
                current_trade = {
                    'id': trade_id,
                    'entry_time': entry_time,
                    'entry_price': entry_price,
                    'side': side,
                    'exit_time': None,
                    'exit_price': None,
                    'result': None
                }
                
                trades.append({
                    'codigo_operacao': trade_id,
                    'data_hora': entry_time,
                    'tipo': trade_type,
                    'lado': side,
                    'preco': entry_price,
                    'resultado': result,
                    'saldo': balance
                })
                trade_id_counter += 1
                print(f"Entrada em venda: {entry_time} | Preço: {entry_price:.5f}")

    # Verificar saída (antes de 18h ou mudança de dia)
    if current_trade is not None:
        current_time = row.name
        
        # Se for novo dia, encerra
        if current_time.date() != current_trade['entry_time'].date():
            exit_price = row['open_price']  # fechar no início do novo dia
            profit_per_contract = (current_trade['entry_price'] - exit_price) * contract_size * tick_value
            total_profit = profit_per_contract
            balance += total_profit
            current_trade['exit_time'] = current_time
            current_trade['exit_price'] = exit_price
            current_trade['result'] = total_profit

            trades.append({
                'codigo_operacao': current_trade['id'],
                'data_hora': current_time,
                'tipo': 'saida',
                'lado': 'venda',
                'preco': exit_price,
                'resultado': total_profit,
                'saldo': balance
            })

            print(f"Saida: {current_time} | Preço: {exit_price:.5f} | Lucro: R${total_profit:.2f}")
            current_trade = None

        # Se já passou das 18h, vende
        elif row['hour'] >= exit_hour:
            exit_price = row['close_price']
            profit_per_contract = (current_trade['entry_price'] - exit_price) * contract_size * tick_value
            total_profit = profit_per_contract
            balance += total_profit
            current_trade['exit_time'] = current_time
            current_trade['exit_price'] = exit_price
            current_trade['result'] = total_profit

            trades.append({
                'codigo_operacao': current_trade['id'],
                'data_hora': current_time,
                'tipo': 'saida',
                'lado': 'venda',
                'preco': exit_price,
                'resultado': total_profit,
                'saldo': balance
            })

            print(f"Saida: {current_time} | Preço: {exit_price:.5f} | Lucro: R${total_profit:.2f}")
            current_trade = None

# Finalizar operações abertas
if current_trade:
    last_row = data.iloc[-1]
    exit_price = last_row['close_price']
    profit_per_contract = (current_trade['entry_price'] - exit_price) * contract_size * tick_value
    total_profit = profit_per_contract
    balance += total_profit
    current_trade['exit_time'] = last_row.name
    current_trade['exit_price'] = exit_price
    current_trade['result'] = total_profit

    trades.append({
        'codigo_operacao': current_trade['id'],
        'data_hora': current_trade['exit_time'],
        'tipo': 'saida',
        'lado': 'venda',
        'preco': exit_price,
        'resultado': total_profit,
        'saldo': balance
    })

# Criar DataFrame com resultados
df_trades = pd.DataFrame(trades)

# Exibir saldo final
print(f"\nSaldo Inicial: R$ {initial_balance:.2f}")
print(f"Saldo Final: R$ {balance:.2f}")
print(f"Lucro Total: R$ {balance - initial_balance:.2f}")
print(f"Total de operações: {len(df_trades) // 2}")

# Exportar para CSV
df_trades.to_csv('backtest_resultados.csv', index=False, encoding='utf-8-sig')
print("\nResultado exportado para 'backtest_resultados.csv'")

# Fechar MT5
mt5.shutdown()