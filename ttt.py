import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

# === CONFIGURAÇÕES INICIAIS ===

symbol = "WIN$N"  # Mini-índice genérico
timeframe = mt5.TIMEFRAME_M5  # 5 minutos
start_date = datetime(2024, 1, 1)
end_date = datetime(2024, 6, 1)

# === CONECTAR AO MT5 ===

if not mt5.initialize():
    print("initialize() failed")
    mt5.shutdown()

# Coletar dados
rates = mt5.copy_rates_range(symbol, timeframe, start_date, end_date)
mt5.shutdown()

# Converter para DataFrame
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

# Calcular SMA de 20 períodos
df['sma20'] = df['close'].rolling(20).mean()

# === FUNÇÕES DE PADRÕES ===

def is_bullish_pattern(mins):
    if mins[1] > mins[0] and mins[2] > mins[1]:
        diffs = [mins[1] - mins[0], mins[2] - mins[1]]
        media_diffs = np.mean([abs(d) for d in diffs])
        return media_diffs / mins[0] <= 0.1
    return False

def is_bearish_pattern(maxs):
    if maxs[1] < maxs[0] and maxs[2] < maxs[1]:
        diffs = [maxs[1] - maxs[0], maxs[2] - maxs[1]]
        media_diffs = np.mean([abs(d) for d in diffs])
        return media_diffs / maxs[0] <= 0.1
    return False

# === BACKTEST ===

trades = []
i = 2

while i < len(df) - 1:
    row1 = df.iloc[i - 2]
    row2 = df.iloc[i - 1]
    row3 = df.iloc[i]

    mins = [row1['low'], row2['low'], row3['low']]
    maxs = [row1['high'], row2['high'], row3['high']]

    # Compra
    if is_bullish_pattern(mins):
        entry_price = df.iloc[i + 1]['open']
        stop = row2['low']
        risk = entry_price - stop
        tp1 = entry_price + 2 * risk
        partial_done = False

        for j in range(i + 1, len(df)):
            high = df.iloc[j]['high']
            low = df.iloc[j]['low']
            close = df.iloc[j]['close']
            sma = df.iloc[j]['sma20']

            if low <= stop:
                trades.append({
                    "type": "buy",
                    "entry": entry_price,
                    "stop": stop,
                    "partial": None,
                    "final": stop,
                    "exit_type": "stop"
                })
                break

            if not partial_done and high >= tp1:
                partial_done = True

            if partial_done and close < sma:
                trades.append({
                    "type": "buy",
                    "entry": entry_price,
                    "stop": stop,
                    "partial": tp1,
                    "final": close,
                    "exit_type": "ma_cross"
                })
                break

    # Venda
    if is_bearish_pattern(maxs):
        entry_price = df.iloc[i + 1]['open']
        stop = row2['high']
        risk = stop - entry_price
        tp1 = entry_price - 2 * risk
        partial_done = False

        for j in range(i + 1, len(df)):
            high = df.iloc[j]['high']
            low = df.iloc[j]['low']
            close = df.iloc[j]['close']
            sma = df.iloc[j]['sma20']

            if high >= stop:
                trades.append({
                    "type": "sell",
                    "entry": entry_price,
                    "stop": stop,
                    "partial": None,
                    "final": stop,
                    "exit_type": "stop"
                })
                break

            if not partial_done and low <= tp1:
                partial_done = True

            if partial_done and close > sma:
                trades.append({
                    "type": "sell",
                    "entry": entry_price,
                    "stop": stop,
                    "partial": tp1,
                    "final": close,
                    "exit_type": "ma_cross"
                })
                break

    i += 1

# === RESULTADOS ===

results = pd.DataFrame(trades)
results["risk"] = abs(results["entry"] - results["stop"])
results["profit"] = 0.5 * (results["partial"] - results["entry"]).fillna(0) + 0.5 * (results["final"] - results["entry"])
results["profit"] = np.where(results["type"] == "sell", -results["profit"], results["profit"])

# Cálculo do Profit Factor
total_profit = results[results["profit"] > 0]["profit"].sum()
total_loss = abs(results[results["profit"] < 0]["profit"].sum())
profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

# Print do resumo
print("====== RESULTADOS DO BACKTEST ======")
print("Total de trades:", len(results))
print("Taxa de acerto: {:.2f}%".format(len(results[results["profit"] > 0]) / len(results) * 100))
print("Lucro total (pontos):", results["profit"].sum())
print("Média por trade:", results["profit"].mean())
print("Profit Factor:", round(profit_factor, 2))

# Salvar em CSV se quiser
# results.to_csv("resultado_backtest_win.csv", index=False)
