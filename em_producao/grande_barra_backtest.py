# -*- coding: utf-8 -*-
"""
Backtest para o Mini Índice Brasileiro (WIN) usando MetaTrader5 + Python
Regras:
- Entrada quando aparecer uma barra cujo CORPO (|close-open|) seja >= N × média dos corpos das últimas 10 barras.
  • Se a barra for de alta (close > open) → COMPRA no fechamento da própria barra.
  • Se for de baixa (close < open) → VENDA no fechamento da própria barra.
  • Permite testar vários N (ex.: [4.0, 5.0, 6.0]).

- Saída quando:
  • Ocorrer uma sequência de 3 barras consecutivas no sentido CONTRÁRIO à posição, OU
  • Surgir nova ENTRADA no sentido contrário (fecha a atual e entra no novo sentido no fechamento da barra do novo sinal), OU
  • Chegar 18:00 (fecha a posição aberta), OU
  • Trocar o dia (se a próxima barra pertencer a um novo dia, fecha a posição na ÚLTIMA barra do dia anterior), OU
  • Fim do período.

- Day trade: encerrar tudo às 18:00.
- 1 contrato por operação.
- Tick do WIN: passo de 5 pontos; 1 ponto = R$0,20 → 5 pontos (1 tick) = R$1,00.
- Saldo inicial: R$ 1.000,00.
- Geração de CSV: uma linha para ENTRADA e outra para SAÍDA, com mesmo "Código da operação".

IMPORTANTE:
- Este script precisa do terminal MetaTrader 5 instalado e com o símbolo do WIN habilitado no Market Watch.
- O fuso horário das barras retornadas pelo MT5 depende da corretora/plataforma; ajuste se necessário.
"""

from __future__ import annotations
import MetaTrader5 as MT5
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from pathlib import Path
import pytz

# =============================
# ===== Parâmetros Gerais =====
# =============================
SYMBOL = "WINV25"               # Ajuste para o código vigente (ex.: WINQ25). Você pode automatizar se já tiver função pronta.
TIMEFRAME = MT5.TIMEFRAME_M5    # M1, M5, M15, etc.
DT_START = datetime(2024, 8, 10) # Data inicial
DT_END   = datetime(2025, 9, 11) # Data final (inclusiva na consulta; ver copyRatesRange)

BIG_BODY_MULTIPLIERS = [5.0]    # Permite testar vários N (ex.: [4.0, 5.0, 6.0])
ROLL_WINDOW = 10                # média dos últimos 10 corpos

CLOSE_ALL_AT = time(18, 0)      # Encerrar tudo às 18:00
POINT_VALUE_R = 0.20            # R$ por ponto
PRICE_STEP = 5                  # preço do WIN varia de 5 em 5 pontos
START_BALANCE = 1000.0
CSV_DIR = Path("./backtests_win_corpo_gt_mediaN")
CSV_DIR.mkdir(parents=True, exist_ok=True)

# =============================
# ===== Funções utilitárias ===
# =============================



def round_to_step(price: float, step: int = PRICE_STEP) -> float:
    """Arredonda o preço para o múltiplo de step mais próximo."""
    return step * round(price / step)


def pnl_reais(entry_price: float, exit_price: float, side: int) -> float:
    """Calcula PnL em R$ para 1 contrato.
    side: +1 para comprado, -1 para vendido
    """
    diff_points = (exit_price - entry_price) * side
    return diff_points * POINT_VALUE_R


def ensure_mt5_initialized() -> None:
    if not MT5.initialize():
        raise RuntimeError(f"Falha ao inicializar MT5: {MT5.last_error()}")

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
        dados = MT5.copy_rates_range(ativo, timeframe, from_utc, to_utc)
        
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


def get_rates(symbol: str, timeframe, dt_start: datetime, dt_end: datetime) -> pd.DataFrame:
    """Baixa candles do MT5 e devolve DataFrame com colunas usuais."""
    # copyRatesRange inclui a barra do início e exclui a do fim? Depende da build.
    # Para segurança, adicionamos +1 dia no final e depois filtramos.
    # dt_end_plus = dt_end + timedelta(days=1)
    # timezone = pytz.timezone("America/Sao_Paulo")
    # dt_start = timezone.localize(dt_start).astimezone(pytz.utc)
    # dt_end_plus = timezone.localize(dt_end_plus).astimezone(pytz.utc)
    # rates = MT5.copy_rates_range(symbol, timeframe, dt_start, dt_end_plus)
    # if rates is None or len(rates) == 0:
    #     raise RuntimeError(f"Sem dados para {symbol} no período solicitado. Erro: {MT5.last_error()}")
    # df = pd.DataFrame(rates)
    # df['time'] = pd.to_datetime(df['time'], unit='s')
    ###################
    df = buscar_dados_em_blocos(symbol,timeframe,dt_start,dt_end)

    # Filtra estritamente pelo intervalo desejado
    #df = df[(df['time'] >= dt_start) & (df['time'] <= dt_end)]
    df = df.reset_index(drop=True)
    # Normaliza preços ao step (por garantia)
    for col in ['open', 'high', 'low', 'close']:
        df[col] = (df[col] / PRICE_STEP).round() * PRICE_STEP
    return df


def add_signal_columns(df: pd.DataFrame, roll_window: int, multiplier: float) -> pd.DataFrame:
    """Adiciona colunas de corpo, média móvel dos corpos e sinal de grande barra (up/down)."""
    df = df.copy()
    df['body'] = (df['close'] - df['open']).astype(float)
    df['body_abs'] = df['body'].abs()
    # média dos últimos N corpos, EXCLUINDO a barra atual → usa shift(1)
    df['avg_body_prevN'] = df['body_abs'].shift(1).rolling(roll_window, min_periods=roll_window).mean()
    cond_big = df['avg_body_prevN'].notna() & (df['body_abs'] >= multiplier * df['avg_body_prevN'])
    df['big_up'] = cond_big & (df['body'] > 0)
    df['big_dn'] = cond_big & (df['body'] < 0)
    # Gera sinal numérico: +1 compra, -1 venda, 0 nada
    df['sig'] = 0
    df.loc[df['big_up'], 'sig'] = 1
    df.loc[df['big_dn'], 'sig'] = -1
    return df


# ==========================================
# ===== Núcleo do Backtest (loop single) ===
# ==========================================

def run_backtest(df: pd.DataFrame, multiplier: float) -> tuple[pd.DataFrame, float]:
    """Roda o backtest para um dado multiplicador e retorna (trades_df, saldo_final)."""
    pos = 0               # 0 sem posição, +1 long, -1 short
    entry_price = None
    entry_time = None
    op_code = 0
    consec_opposite = 0   # contador de barras consecutivas contra a posição

    balance = START_BALANCE

    rows = []  # para o CSV: uma linha por transação (entrada ou saída)

    def register_entry(ts, side, price):
        nonlocal op_code, entry_price, entry_time, pos
        op_code += 1
        code = f"OP{op_code:05d}"
        pos = side
        entry_price = price
        entry_time = ts
        rows.append({
            'Código da operação': code,
            'Data e hora': ts,
            'Tipo': 'Entrada',
            'Lado': 'Compra' if side == 1 else 'Venda',
            'Preço': float(price),
            'Resultado': 0.0,
            'Saldo': balance
        })
        return code

    def register_exit(ts, price, code):
        nonlocal balance
        side = 1 if 'Compra' in [r['Lado'] for r in rows if r['Código da operação'] == code][:1] else -1
        result = pnl_reais(entry_price, price, side)
        balance += result
        rows.append({
            'Código da operação': code,
            'Data e hora': ts,
            'Tipo': 'Saída',
            'Lado': 'Compra' if side == 1 else 'Venda',
            'Preço': float(price),
            'Resultado': float(result),
            'Saldo': float(balance)
        })

    prev_dt = None
    current_op_code = None

    for i in range(len(df)):
        bar = df.iloc[i]
        ts: pd.Timestamp = bar['time']
        dt = ts.to_pydatetime()

        # 1) Se mudou de dia e temos posição, fechar na barra ANTERIOR (última do dia anterior)
        if prev_dt is not None and dt.date() != prev_dt.date() and pos != 0:
            # fecha na close da barra anterior
            prev_close = df.iloc[i-1]['close']
            prev_ts = df.iloc[i-1]['time']
            exit_price = round_to_step(prev_close)
            register_exit(prev_ts, exit_price, current_op_code)
            pos = 0
            entry_price = None
            current_op_code = None
            consec_opposite = 0

        # 2) Se já passou das 18:00 no dia e há posição, fecha nesta barra
        if pos != 0 and dt.time() >= CLOSE_ALL_AT:
            exit_price = round_to_step(bar['close'])
            register_exit(ts, exit_price, current_op_code)
            pos = 0
            entry_price = None
            current_op_code = None
            consec_opposite = 0
            # depois de 18:00 não abrimos mais
            prev_dt = dt
            continue

        # 3) Lógica de contagem de 3 barras contra
        if pos != 0:
            is_bear = bar['close'] < bar['open']
            is_bull = bar['close'] > bar['open']
            against = (pos == 1 and is_bear) or (pos == -1 and is_bull)
            if against:
                consec_opposite += 1
            else:
                consec_opposite = 0

            if consec_opposite >= 3:
                # fecha no fechamento da 3ª barra contrária
                exit_price = round_to_step(bar['close'])
                register_exit(ts, exit_price, current_op_code)
                pos = 0
                entry_price = None
                current_op_code = None
                consec_opposite = 0
                # após sair por 3 contrárias, pode avaliar novo sinal nesta mesma barra? 
                # Pela regra, a saída ocorre devido à sequência; não reentra nesta mesma barra a menos que haja sinal contrário explícito.

        # 4) Sinal de grande barra nesta barra
        sig = int(bar['sig']) if not np.isnan(bar['sig']) else 0
        if dt.time() < CLOSE_ALL_AT:  # não abre depois das 18:00
            if pos == 0 and sig != 0:
                current_op_code = register_entry(ts, sig, round_to_step(bar['close']))
            elif pos != 0 and sig != 0 and np.sign(pos) != np.sign(sig):
                # Sinal oposto: fecha atual e entra no novo sentido
                exit_price = round_to_step(bar['close'])
                register_exit(ts, exit_price, current_op_code)
                pos = 0
                entry_price = None
                consec_opposite = 0
                # entra no novo
                current_op_code = register_entry(ts, sig, round_to_step(bar['close']))

        prev_dt = dt

    # Final do dataset: se ficou posição aberta, fecha na última barra
    if len(df) > 0 and pos != 0:
        last_bar = df.iloc[-1]
        register_exit(last_bar['time'], round_to_step(last_bar['close']), current_op_code)

    trades = pd.DataFrame(rows)
    trades = trades[[
        'Código da operação', 'Data e hora', 'Tipo', 'Lado', 'Preço', 'Resultado', 'Saldo'
    ]]
    return trades, balance


# ==========================================
# ===== Runner para vários N (multiplier) ===
# ==========================================

def main():
    ensure_mt5_initialized()

    # Garante símbolo selecionado no MT5
    MT5.symbol_select(SYMBOL, True)

    raw = get_rates(SYMBOL, TIMEFRAME, DT_START, DT_END)

    results_summary = []

    for mult in BIG_BODY_MULTIPLIERS:
        df = add_signal_columns(raw, ROLL_WINDOW, mult)
        trades, final_balance = run_backtest(df, mult)

        csv_path = CSV_DIR / f"{SYMBOL}_TF{int(TIMEFRAME)}_N{mult:.2f}_{DT_START:%Y%m%d}_{DT_END:%Y%m%d}.csv"
        # Formata Data e hora como string ISO para o CSV
        trades_out = trades.copy()
        trades_out['Data e hora'] = trades_out['Data e hora'].dt.strftime('%Y-%m-%d %H:%M:%S')
        trades_out.to_csv(csv_path, index=False, encoding='utf-8')

        results_summary.append({
            'N (multiplicador)': mult,
            'Operações': trades['Código da operação'].nunique(),
            'Trades (linhas)': len(trades),
            'Saldo final (R$)': round(final_balance, 2),
            'CSV': str(csv_path)
        })

    summary_df = pd.DataFrame(results_summary)
    print("Resumo dos testes:")
    print(summary_df.to_string(index=False))

    MT5.shutdown()


if __name__ == "__main__":
    main()
