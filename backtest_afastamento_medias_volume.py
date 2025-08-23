# backtest_win_mm200.py
# Requisitos: pip install MetaTrader5 pandas numpy pytz

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import os
import math
from typing import List, Tuple

# ------------------------------
# Configurações gerais
# ------------------------------
BR_TIMEZONE = "America/Sao_Paulo"
INITIAL_BALANCE = 1000.00  # R$ 1.000,00
POINT_VALUE = 0.20         # R$0,20 por ponto
TICK_SIZE = 5              # WIN varia em múltiplos de 5 pontos
MM_PERIOD = 200
LOOKBACK_BODY_VOL = 10     # comparar corpo e volume com últimas 10 barras
ENTRY_START_HHMM = (14, 0) # 14:00
CLOSE_ALL_HHMM  = (18, 0)  # 18:00
ONE_CONTRACT = 1

# ------------------------------
# Utilitários
# ------------------------------
def nearest_tick(price: float, tick_size: int = TICK_SIZE) -> float:
    """Arredonda para o múltiplo de tick mais próximo."""
    return round(price / tick_size) * tick_size

def to_brt(dt_utc: pd.Series) -> pd.Series:
    """Converte timestamps UTC para America/Sao_Paulo (com DST)."""
    #return pd.to_datetime(dt_utc, unit="s", utc=True).dt.tz_convert(BR_TIMEZONE)
    return pd.to_datetime(dt_utc, unit="s")

def ensure_mt5_initialized():
    if not mt5.initialize():
        raise RuntimeError(f"Falha ao inicializar MT5: {mt5.last_error()}")
    # opcionalmente: mt5.login(login, password, server)

def shutdown_mt5():
    try:
        mt5.shutdown()
    except:
        pass

def month_range(start: datetime, end: datetime) -> List[Tuple[datetime, datetime]]:
    """Divide [start, end] em blocos mensais (inclusivos) para evitar limites do broker."""
    blocks = []
    cur = datetime(start.year, start.month, 1, tzinfo=pytz.UTC)
    end_utc = end
    if end_utc.tzinfo is None:
        end_utc = pytz.UTC.localize(end_utc)
    while cur <= end_utc:
        next_month = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        block_end = min(next_month - timedelta(seconds=1), end_utc)
        block_start = max(cur, start)
        blocks.append((block_start, block_end))
        cur = next_month
    return blocks

def fetch_rates_range(symbol: str, timeframe: int, date_from_local: datetime, date_to_local: datetime) -> pd.DataFrame:
    """
    Baixa candles em blocos mensais para o período desejado.
    As datas passadas devem estar no timezone local (America/Sao_Paulo).
    """
    tz = pytz.timezone(BR_TIMEZONE)
    if date_from_local.tzinfo is None:
        date_from_local = tz.localize(date_from_local)
    if date_to_local.tzinfo is None:
        date_to_local = tz.localize(date_to_local)
    date_from_utc = date_from_local.astimezone(pytz.UTC)
    date_to_utc   = date_to_local.astimezone(pytz.UTC)

    ensure_mt5_initialized()
    all_df = []
    try:
        for block_start, block_end in month_range(date_from_utc, date_to_utc):
            rates = mt5.copy_rates_range(symbol, timeframe, block_start, block_end)
            if rates is None or len(rates) == 0:
                continue
            df = pd.DataFrame(rates)
            all_df.append(df)
    finally:
        shutdown_mt5()

    if not all_df:
        raise RuntimeError("Nenhum dado foi retornado para o período especificado.")

    data = pd.concat(all_df, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    # Colunas padrão: time, open, high, low, close, tick_volume, spread, real_volume
    data["datetime"] = to_brt(data["time"])
    data.set_index("datetime", inplace=True)
    return data[["open", "high", "low", "close", "tick_volume", "real_volume", "spread"]]

def compute_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()

def is_down_bar(row) -> bool:
    return row["close"] < row["open"]

def bar_body(row) -> float:
    return abs(row["close"] - row["open"])

def within_trading_window(ts: pd.Timestamp) -> bool:
    hh, mm = ts.hour, ts.minute
    # Entradas podem ocorrer somente entre 14:00 e 17:59:59 (antes do fechamento de 18:00)
    start_h, start_m = ENTRY_START_HHMM
    end_h, end_m = CLOSE_ALL_HHMM
    start_ok = (hh > start_h) or (hh == start_h and mm >= start_m)
    end_ok = (hh < end_h) or (hh == end_h and mm < end_m)
    return start_ok and end_ok

def is_close_time(ts: pd.Timestamp) -> bool:
    # Força zeragem às 18:00 (ou na última barra do dia)
    end_h, end_m = CLOSE_ALL_HHMM
    return ts.hour > end_h or (ts.hour == end_h and ts.minute >= end_m)

def pnl_brl(entry_price: float, exit_price: float, side: str) -> float:
    """
    Calcula PnL em R$ para 1 contrato.
    side: 'compra' ou 'venda'
    WIN: R$0,20 por ponto (1 ponto); o preço já está em pontos.
    """
    diff_points = (exit_price - entry_price) if side == "compra" else (entry_price - exit_price)
    return diff_points * POINT_VALUE * ONE_CONTRACT

# ------------------------------
# Lógica do backtest
# ------------------------------
def backtest_win(
    df: pd.DataFrame,
    x_list: List[float],
    csv_prefix: str,
) -> pd.DataFrame:
    """
    Executa o backtest para cada x em x_list.
    - df deve conter colunas: open, high, low, close, tick_volume
    - Gera um CSV por x e retorna um resumo com saldo final por x
    """
    # Preparo de indicadores
    df = df.copy()
    df["sma200"] = compute_sma(df["close"], MM_PERIOD)
    df["body"] = (df["close"] - df["open"]).abs()
    df["vol"] = df["tick_volume"].astype(float)

    # Para comparação com últimas 10 barras (exclui a atual)
    df["max_body_10"] = df["body"].shift(1).rolling(LOOKBACK_BODY_VOL, min_periods=LOOKBACK_BODY_VOL).max()
    df["max_vol_10"]  = df["vol"].shift(1).rolling(LOOKBACK_BODY_VOL, min_periods=LOOKBACK_BODY_VOL).max()

    # Removemos período antes de ter MM200 válida
    df = df.dropna(subset=["sma200", "max_body_10", "max_vol_10"])

    summaries = []

    for x in x_list:
        balance = INITIAL_BALANCE
        in_position = False
        side = None        # 'venda' (somente venda neste setup)
        entry_price = None
        op_code = 0
        trade_day = None
        rows = []  # para o CSV

        # Funções internas para registrar transações
        def log_txn(op_code, ts, tipo, lado, preco, resultado=None, saldo=None):
            rows.append({
                "Código da operação": op_code,
                "Data e hora": ts.strftime("%Y-%m-%d %H:%M:%S%z"),
                "Tipo": tipo,   # "Entrada" ou "Saída"
                "Lado": lado,   # "Compra" ou "Venda"
                "Preço": float(preco),
                "Resultado": (None if resultado is None else float(round(resultado, 2))),
                "Saldo": (None if saldo is None else float(round(saldo, 2))),
            })

        # Loop principal barra a barra
        for ts, row in df.iterrows():
            # Controle de day trade: se mudou o dia e temos posição, zerar na barra anterior (aqui na abertura/fech. disponível)
            if in_position and trade_day is not None and ts.date() != trade_day:
                # Saída na abertura desta barra (ou no último preço da barra anterior; aqui usamos o preço de abertura da barra do novo dia)
                exit_price = nearest_tick(row["open"])
                result = pnl_brl(entry_price, exit_price, side)
                balance += result
                log_txn(op_code, ts, "Saída", side, exit_price, result, balance)
                in_position = False
                side = None
                entry_price = None
                trade_day = None

            # Se horário >= 18:00 e estamos posicionados, zerar na primeira barra que iguale/ultrapasse 18:00
            if in_position and is_close_time(ts):
                exit_price = nearest_tick(row["close"])
                result = pnl_brl(entry_price, exit_price, side)
                balance += result
                log_txn(op_code, ts, "Saída", side, exit_price, result, balance)
                in_position = False
                side = None
                entry_price = None
                trade_day = None
                continue  # próxima barra

            sma200 = row["sma200"]

            # Gestão da posição (saída no retorno à MM200)
            if in_position:
                # Se durante a barra tocou/voltou à MM200, consideramos saída ao preço da MM200 (arredondado ao tick)
                # Critério: para 'venda', se low <= sma200 (tocou para baixo)
                if row["low"] <= sma200 <= row["high"]:
                    exit_price = nearest_tick(sma200)
                    result = pnl_brl(entry_price, exit_price, side)
                    balance += result
                    log_txn(op_code, ts, "Saída", side, exit_price, result, balance)
                    in_position = False
                    side = None
                    entry_price = None
                    trade_day = None
                    continue
                # Alternativamente, se close já voltou abaixo da MM200
                if row["close"] <= sma200:
                    exit_price = nearest_tick(row["close"])
                    result = pnl_brl(entry_price, exit_price, side)
                    balance += result
                    log_txn(op_code, ts, "Saída", side, exit_price, result, balance)
                    in_position = False
                    side = None
                    entry_price = None
                    trade_day = None
                    continue

            # Sinais de entrada (somente se não posicionado e dentro da janela 14:00–18:00)
            if (not in_position) and within_trading_window(ts):
                # Afastamento para cima x% ou mais da MM200
                # Usaremos o CLOSE da barra como referência de afastamento
                if row["close"] >= sma200 * (1.0 + x):
                    # Barra de baixa (close < open)
                    if is_down_bar(row):
                        # Corpo e volume maiores que as últimas 10 barras
                        if (row["body"] > row["max_body_10"]) and (row["vol"] > row["max_vol_10"]):
                            # ENTRADA: venda a mercado ao preço de fechamento (arredondado ao tick)
                            entry_price = nearest_tick(row["close"])
                            side = "venda"
                            in_position = True
                            op_code += 1
                            trade_day = ts.date()
                            log_txn(op_code, ts, "Entrada", side, entry_price, resultado=None, saldo=balance)

        # Se terminar o loop ainda posicionado, força zeragem no último candle
        if in_position:
            last_ts, last = df.iloc[-1].name, df.iloc[-1]
            exit_price = nearest_tick(last["close"])
            result = pnl_brl(entry_price, exit_price, side)
            balance += result
            log_txn(op_code, last_ts, "Saída", side, exit_price, result, balance)
            in_position = False

        # Salvar CSV
        os.makedirs("results", exist_ok=True)
        csv_path = os.path.join("results", f"{csv_prefix}_x{str(round(x,4)).replace('.', '_')}.csv")
        out_df = pd.DataFrame(rows, columns=[
            "Código da operação",
            "Data e hora",
            "Tipo",
            "Lado",
            "Preço",
            "Resultado",
            "Saldo"
        ])
        out_df.to_csv(csv_path, index=False, encoding="utf-8")
        summaries.append({
            "x": x,
            "saldo_final": round(balance, 2),
            "csv": csv_path,
            "num_operacoes": int(out_df[out_df["Tipo"] == "Entrada"].shape[0]),
        })

    return pd.DataFrame(summaries).sort_values("x")

# ------------------------------
# Execução exemplo
# ------------------------------
if __name__ == "__main__":
    # 🛠️ Ajuste estes parâmetros:
    SYMBOL = "WIN$"                    # ou "WINQ25", etc. Use seu código corrente.
    TIMEFRAME = mt5.TIMEFRAME_M15       # M1/M5/M15... à sua escolha
    DATE_FROM = datetime(2020, 8, 18, 0, 0)  # início (horário local BRT)
    DATE_TO   = datetime(2025, 8, 14, 23, 59) # fim (horário local BRT)
    X_LIST = [0.005, 0.01, 0.015]      # 0.5%, 1.0%, 1.5%

    print("Baixando dados do MT5...")
    data = fetch_rates_range(SYMBOL, TIMEFRAME, DATE_FROM, DATE_TO)

    # Filtrar somente pregões (opcional): B3 normalmente 10:00–18:00 BRT; aqui só precisamos garantir que dados incluem 14–18h
    # Rodar o backtest
    prefix = f"{SYMBOL}_{TIMEFRAME}_from_{DATE_FROM.strftime('%Y%m%d')}_to_{DATE_TO.strftime('%Y%m%d')}"
    print("Executando backtests...")
    resumo = backtest_win(data, X_LIST, prefix)

    print("\nResumo por x:")
    print(resumo.to_string(index=False))
    print("\nArquivos CSV gerados em ./results/")
