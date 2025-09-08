# -*- coding: utf-8 -*-
"""
Backtest: Mini Índice (WIN) via Python + MetaTrader5
Lógica: Entrar quando o ângulo da SMA estiver acima/abaixo de um limite e sair quando
o ângulo perder a inclinação (ficar abaixo do limite em módulo).
- Fechamento diário obrigatório (18:00) e sem carregar posição para o dia seguinte.
- 1 contrato por operação. Tick do WIN: 5 pontos; cada ponto = R$ 0,20; cada tick = R$ 1,00.
- Gera CSV detalhado das transações e um resumo no console.

Requisitos:
- pip install MetaTrader5 pandas numpy pytz
- MT5 aberto/logado no mesmo computador OU usar login() no início.

Observações importantes sobre o "ângulo":
O conceito de ângulo depende da escala do gráfico. Para evitar ambiguidades,
o script oferece dois modos de cálculo:
  1) angle_mode = "points_per_bar": usa a variação da SMA por barra em "pontos" (preço do WIN)
     ângulo_deg = degrees(atan(delta_SMA_points))  # onde delta = SMA[t] - SMA[t-1]
  2) angle_mode = "atr_scaled": normaliza a variação da SMA pelo ATR(14) (em pontos) da barra
     ângulo_deg = degrees(atan(delta_SMA_points / ATR_points))
Escolha o modo e ajuste o threshold (ex.: 30°) conforme o timeframe.

Autor: (gerado por assistente)
"""

import os
import math
import uuid
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import pytz

# =============================
# ======== PARÂMETROS =========
# =============================

SYMBOL = "WIN$"           # Ajuste conforme sua corretora (ex.: "WINQ25", "WIN$N", etc.)
TIMEFRAME = mt5.TIMEFRAME_M5   # Altere se desejar (M1, M5, M15...)
DATE_FROM = datetime(2020, 9, 1)   # Data inicial do teste (ano, mês, dia)
DATE_TO   = datetime(2025, 9, 1)  # Data final do teste (inclusive até 23:59)

# Você pode testar múltiplos valores de SMA e de ângulo em um grid:
SMA_PERIODS_LIST = [55, 89]          # inclua outros valores, ex.: [9, 14, 21, 34]
ANGLE_THRESH_LIST = [5, 10, 15]     # em graus; inclua outros, ex.: [20.0, 30.0, 40.0]

# Modo de cálculo do ângulo: "points_per_bar" ou "atr_scaled"
ANGLE_MODE = "atr_scaled"

# Encerramento diário obrigatório às 18:00 (horário local). Não carrega posição para o próximo dia.
DAY_END_TIME = time(18, 0, 0)

# Financeiro do WIN:
POINT_VALUE_BR = 0.20   # R$ por 1 ponto
TICK_SIZE_PTS = 5       # tamanho do tick em pontos (variação mínima de preço)
TICK_VALUE_BR = 1.00    # R$ por tick (5 pontos)

# Gestão de capital:
INITIAL_BALANCE = 1000.00  # R$
CONTRACTS = 1              # sempre 1 contrato conforme escopo

# Saída
OUTPUT_DIR = os.path.abspath(".")  # pasta atual; ajuste se quiser


# =============================
# ======= FUNÇÕES BASE ========
# =============================

def connect_mt5():
    if not mt5.initialize():
        raise RuntimeError(f"Falha ao inicializar MT5: {mt5.last_error()}")
    # Caso precise logar explicitamente (conta demo/real), descomente e preencha:
    # if not mt5.login(login=12345678, password="SENHA", server="NOME-DO-SERVIDOR"):
    #     raise RuntimeError(f"Falha ao logar na conta: {mt5.last_error()}")

def buscar_dados_em_blocos(ativo, timeframe, data_inicial, data_final):
    """
    Busca dados no MT5 em blocos mensais e junta tudo em um único DataFrame.
    
    ativo         -> símbolo no MT5, ex: "WINQ25"
    timeframe     -> ex: mt5.TIMEFRAME_M1
    data_inicial  -> datetime no fuso de São Paulo
    data_final    -> datetime no fuso de São Paulo
    """
    
    timezone = pytz.timezone("America/Sao_Paulo")
    data_atual = data_inicial
    todos_dados = []

    while data_atual < data_final:
        # Define intervalo de no máximo 30 dias
        proximo_mes = min(data_atual + timedelta(days=30), data_final)
        
        # Converter para UTC
        from_utc = timezone.localize(data_atual).astimezone(pytz.utc)
        to_utc = timezone.localize(proximo_mes).astimezone(pytz.utc)
        
        # Buscar dados no MT5
        dados = mt5.copy_rates_range(ativo, timeframe, from_utc, to_utc)
        
        if dados is not None and len(dados) > 0:
            df = pd.DataFrame(dados)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            todos_dados.append(df)
        
        # Avança para o próximo bloco
        data_atual = proximo_mes

    # Junta todos os blocos em um único DataFrame
    if todos_dados:
        df_final = pd.concat(todos_dados).drop_duplicates(subset=['time']).reset_index(drop=True)
        return df_final
    else:
        return pd.DataFrame()

def fetch_rates(symbol, timeframe, date_from, date_to):
    # MT5 copy_rates_range inclui a barra cujo time >= date_from e < date_to?
    # Por segurança, adicionamos +1 dia ao final para garantir captura até 23:59 do último dia.
    date_to_inclusive = date_to + timedelta(days=1)

    # timezone = pytz.timezone("America/Sao_Paulo")
    # date_to = timezone.localize(date_to).astimezone(pytz.utc)
    # date_to_inclusive = timezone.localize(date_to_inclusive).astimezone(pytz.utc)
    # rates = mt5.copy_rates_range(symbol, timeframe, date_from, date_to_inclusive)
    rates = buscar_dados_em_blocos(symbol,timeframe,date_from,date_to)

    if rates is None or len(rates) == 0:
        raise RuntimeError("Nenhum dado retornado. Verifique símbolo/timeframe/período/mercado.")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.rename(columns={"time":"datetime"}, inplace=True)
    df = df.sort_values("datetime").reset_index(drop=True)
    return df

def sma(series, period):
    return series.rolling(window=period, min_periods=period).mean()

def atr(df, period=14):
    # ATR baseado em OHLC padrão (em pontos do ativo)
    high = df["high"]
    low  = df["low"]
    close= df["close"]
    prev_close = close.shift(1)
    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()

def angle_degrees(delta_points, scale_points=1.0):
    # delta_points: variação da SMA em "pontos" do WIN por barra
    # scale_points: 1.0 para "points_per_bar"; ou ATR_points para "atr_scaled"
    if scale_points is None or scale_points == 0:
        return 0.0
    return math.degrees(math.atan(delta_points / scale_points))

def price_to_reais(price_diff_points):
    # 1 ponto = R$0,20 -> ganho R$ = diff_points * 0.20 * contratos
    return price_diff_points * POINT_VALUE_BR * CONTRACTS

def round_to_tick(price):
    # Garante que preços estejam alinhados ao múltiplo de tick (5 pontos)
    return round(price / TICK_SIZE_PTS) * TICK_SIZE_PTS

# =============================
# ======= CORE BACKTEST =======
# =============================

def run_backtest(df_raw, sma_period, angle_threshold_deg, angle_mode="atr_scaled"):
    df = df_raw.copy()

    # Indicadores
    df[f"SMA_{sma_period}"] = sma(df["close"], sma_period)

    # Precisamos do ATR se for o modo "atr_scaled"
    df["ATR14"] = atr(df, period=14) if angle_mode == "atr_scaled" else np.nan

    # Delta da SMA em pontos por barra
    df["delta_sma"] = df[f"SMA_{sma_period}"] - df[f"SMA_{sma_period}"].shift(1)

    # Escala para o ângulo
    if angle_mode == "atr_scaled":
        df["angle_deg"] = df.apply(
            lambda r: angle_degrees(r["delta_sma"], r["ATR14"]) if pd.notna(r["ATR14"]) else np.nan,
            axis=1
        )
    else:  # "points_per_bar"
        df["angle_deg"] = df["delta_sma"].apply(lambda d: angle_degrees(d, 1.0))

    # Estados de posição
    position = None  # None / "long" / "short"
    entry_price = None
    entry_time  = None
    op_id = None

    # Log de transações
    rows = []  # cada item será dict p/ CSV
    balance = INITIAL_BALANCE

    # Funções auxiliares para registrar
    def log_trade(op_code, dt, tipo, lado, preco, resultado=None):
        nonlocal balance
        if resultado is not None:
            balance += resultado
        rows.append({
            "CodigoOperacao": op_code,
            "DataHora": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "Tipo": tipo,     # "Entrada" ou "Saida"
            "Lado": lado,     # "Compra" / "Venda" / ""
            "Preco": round_to_tick(preco),
            "Resultado": (f"{resultado:.2f}" if resultado is not None else ""),
            "Saldo": f"{balance:.2f}"
        })

    # Loop nas barras
    for i in range(1, len(df)):  # começa em 1 porque usamos shift(1)
        row = df.iloc[i]
        prev = df.iloc[i-1]

        dt = row["datetime"]
        price_close = row["close"]
        price_open  = row["open"]

        sma_angle = row["angle_deg"]
        if pd.isna(sma_angle):
            # Ainda sem dados suficientes
            continue

        # 1) Regras de encerramento por tempo (18:00) ou troca de dia
        must_close = False
        close_reason = None
        if position is not None:
            # Se bateu 18:00 (ou passou), encerra na abertura da barra que marca esse horário
            if dt.time() >= DAY_END_TIME:
                must_close = True
                close_reason = "Fechamento 18:00"
                exit_price = price_open  # fecha na abertura desta barra ao dar 18:00
                exit_time  = dt
            # Se mudou o dia (data diferente da data da entrada), encerra na barra atual (na abertura)
            elif entry_time.date() != dt.date():
                must_close = True
                close_reason = "Virada de dia"
                exit_price = price_open
                exit_time  = dt

        if must_close and position is not None:
            # Calcula PnL em reais
            diff_points = (exit_price - entry_price) if position == "long" else (entry_price - exit_price)
            pnl_reais = price_to_reais(diff_points)
            log_trade(op_id, exit_time, "Saida", "Compra" if position == "long" else "Venda", exit_price, resultado=pnl_reais)
            # Reset posição
            position = None
            entry_price = None
            entry_time  = None
            op_id = None
            # Após fechar por horário/dia, não abrimos nova posição nesta MESMA barra; seguimos p/ próxima.
            continue

        # 2) Lógica de ENTRADA/SAÍDA por ângulo
        # Entradas: se ângulo > +threshold => COMPRA; se ângulo < -threshold => VENDA
        # Saída: se em posição, e |ângulo| < threshold => encerrar na barra atual no CLOSE
        if position is None:
            if sma_angle >= angle_threshold_deg:
                # Abrir COMPRA no fechamento da barra atual
                position = "long"
                entry_price = price_close
                entry_time  = dt
                op_id = str(uuid.uuid4())[:8]
                log_trade(op_id, dt, "Entrada", "Compra", entry_price, resultado=None)
            elif sma_angle <= -angle_threshold_deg:
                # Abrir VENDA no fechamento da barra atual
                position = "short"
                entry_price = price_close
                entry_time  = dt
                op_id = str(uuid.uuid4())[:8]
                log_trade(op_id, dt, "Entrada", "Venda", entry_price, resultado=None)
        else:
            # Já estamos posicionados: checar saída por perda de inclinação
            if abs(sma_angle) < angle_threshold_deg:
                # Sair no fechamento da barra atual
                exit_price = price_close
                diff_points = (exit_price - entry_price) if position == "long" else (entry_price - exit_price)
                pnl_reais = price_to_reais(diff_points)
                log_trade(op_id, dt, "Saida", "Compra" if position == "long" else "Venda", exit_price, resultado=pnl_reais)
                position = None
                entry_price = None
                entry_time  = None
                op_id = None

    # Caso chegue ao fim ainda em posição, encerra na última barra no CLOSE
    if position is not None:
        last = df.iloc[-1]
        dt = last["datetime"]
        exit_price = last["close"]
        diff_points = (exit_price - entry_price) if position == "long" else (entry_price - exit_price)
        pnl_reais = price_to_reais(diff_points)
        log_trade(op_id, dt, "Saida", "Compra" if position == "long" else "Venda", exit_price, resultado=pnl_reais)

    # Converte log em DataFrame
    trades_df = pd.DataFrame(rows, columns=[
        "CodigoOperacao", "DataHora", "Tipo", "Lado", "Preco", "Resultado", "Saldo"
    ])

    # KPIs simples
    # Conta operações completas (pares de entrada/saída por CodigoOperacao)
    grouped = trades_df.groupby("CodigoOperacao")
    op_results = []
    wins = 0
    losses = 0
    for op_code, g in grouped:
        # Resultado está no registro de Saída (se existir)
        g = g.sort_values("DataHora")
        res = 0.0
        if (g["Tipo"] == "Saida").any():
            # pega a primeira saída (deveria haver apenas uma)
            out_row = g[g["Tipo"] == "Saida"].iloc[-1]
            try:
                res = float(out_row["Resultado"].replace(",", "."))
            except:
                res = 0.0
        op_results.append(res)
        if res > 0:
            wins += 1
        elif res < 0:
            losses += 1

    total_ops = len(op_results)
    net = sum(op_results)
    winrate = (wins / total_ops * 100.0) if total_ops > 0 else 0.0
    final_balance = INITIAL_BALANCE + net

    summary = {
        "sma_period": sma_period,
        "angle_threshold_deg": angle_threshold_deg,
        "angle_mode": angle_mode,
        "total_ops": total_ops,
        "wins": wins,
        "losses": losses,
        "winrate_pct": round(winrate, 2),
        "net_result_R$": round(net, 2),
        "final_balance_R$": round(final_balance, 2),
    }

    return trades_df, summary


def main():
    connect_mt5()
    try:
        df = fetch_rates(SYMBOL, TIMEFRAME, DATE_FROM, DATE_TO)
        print(f"Baixou {len(df)} barras de {df['datetime'].min()} até {df['datetime'].max()} para {SYMBOL}.")

        summaries = []
        for sma_p in SMA_PERIODS_LIST:
            for ang_th in ANGLE_THRESH_LIST:
                trades_df, summary = run_backtest(df, sma_p, ang_th, angle_mode=ANGLE_MODE)

                # Nome do arquivo CSV de saída
                fname = f"backtest_{SYMBOL}_TF{TIMEFRAME}_SMA{sma_p}_ANG{int(ang_th)}_{ANGLE_MODE}.csv"
                out_path = os.path.join(OUTPUT_DIR, fname)
                trades_df.to_csv(out_path, index=False, encoding="utf-8")
                print(f"CSV gerado: {out_path} | Operações: {summary['total_ops']} | Net R$: {summary['net_result_R$']:.2f} | Final R$: {summary['final_balance_R$']:.2f}")

                summaries.append(summary)

        # Resumo consolidado
        if summaries:
            sum_df = pd.DataFrame(summaries)
            print("\n==== RESUMO DOS CENÁRIOS TESTADOS ====")
            print(sum_df.to_string(index=False))
            # opcional: salvar também o resumo
            sum_csv = os.path.join(OUTPUT_DIR, f"backtest_{SYMBOL}_resumo.csv")
            sum_df.to_csv(sum_csv, index=False, encoding="utf-8")
            print(f"\nResumo salvo em: {sum_csv}")

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
