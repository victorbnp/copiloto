import pandas as pd
import numpy as np
from tqdm import tqdm

# ===============================
# CONFIGURAÇÕES GERAIS
# ===============================
CSV_FILE = "WIN$_TF5_N5.00_20200815_20250815.csv"
N_SIM_MONTE_CARLO = 5000
INITIAL_CAPITAL = 4000
WFA_SPLITS = 4  # número de janelas para Walk-Forward
SLIPPAGE_RANGE = [-5, 5]  # variação em R$ para robustez paramétrica
RANDOM_SEED = 42

np.random.seed(RANDOM_SEED)

# ===============================
# 1. LEITURA E PREPARAÇÃO DOS DADOS
# ===============================
df = pd.read_csv(CSV_FILE)

# Converte datetime
df['datetime'] = pd.to_datetime(df['datetime'])

# Garante ordenação temporal
df = df.sort_values(by=['datetime'])

# Agrupa operações completas
operacoes = []
for cod, grupo in df.groupby('codigo'):
    grupo = grupo.sort_values('datetime')
    resultado = grupo['resultado_op'].sum()
    data_entrada = grupo.iloc[0]['datetime']
    data_saida = grupo.iloc[-1]['datetime']
    duracao = (data_saida - data_entrada).total_seconds() / 60
    operacoes.append({
        'codigo': cod,
        'entrada': data_entrada,
        'saida': data_saida,
        'lado': grupo.iloc[0]['lado'],
        'resultado': resultado,
        'duracao_min': duracao
    })

ops_df = pd.DataFrame(operacoes)

# ===============================
# Funções auxiliares
# ===============================
def compute_metrics(pnls):
    equity = np.cumsum(np.insert(pnls, 0, INITIAL_CAPITAL))
    returns = np.diff(equity) / equity[:-1]
    total_return = equity[-1] / equity[0] - 1
    sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) != 0 else np.nan
    max_dd = np.min((equity - np.maximum.accumulate(equity)) / np.maximum.accumulate(equity))
    ruin = equity.min() <= 0
    return {
        'final_equity': equity[-1],
        'total_return': total_return,
        'max_drawdown': max_dd,
        'sharpe': sharpe,
        'ruin': ruin
    }

# ===============================
# 2. MONTE CARLO
# ===============================
def monte_carlo(pnls, n_sim=N_SIM_MONTE_CARLO):
    metrics_list = []
    for _ in range(n_sim):
        sim_pnls = np.random.choice(pnls, size=len(pnls), replace=True)
        metrics_list.append(compute_metrics(sim_pnls))
    mc_df = pd.DataFrame(metrics_list)
    return mc_df

mc_results = monte_carlo(ops_df['resultado'].values)
print("\n===== MONTE CARLO =====")
print(mc_results.describe(percentiles=[0.1, 0.5, 0.9]))
print("Probabilidade de Ruína:", mc_results['ruin'].mean())

# ===============================
# 3. ROBUSTEZ PARAMÉTRICA
# ===============================
def robustness_test(pnls, slippage_range):
    results = []
    for slip in slippage_range:
        adj_pnls = pnls + slip
        metrics = compute_metrics(adj_pnls)
        metrics['slippage'] = slip
        results.append(metrics)
    return pd.DataFrame(results)

robust_df = robustness_test(ops_df['resultado'].values, np.linspace(SLIPPAGE_RANGE[0], SLIPPAGE_RANGE[1], 5))
print("\n===== ROBUSTEZ PARAMÉTRICA =====")
print(robust_df)

# ===============================
# 4. WALK-FORWARD ANALYSIS (WFA)
# ===============================
def walk_forward_analysis(ops, splits):
    ops = ops.sort_values('entrada').reset_index(drop=True)
    size = len(ops) // splits
    wf_results = []
    for i in range(splits - 1):
        train = ops.iloc[i*size:(i+1)*size]
        test = ops.iloc[(i+1)*size:(i+2)*size]
        wf_results.append({
            'train_metrics': compute_metrics(train['resultado'].values),
            'test_metrics': compute_metrics(test['resultado'].values)
        })
    return wf_results

wf_results = walk_forward_analysis(ops_df, WFA_SPLITS)
print("\n===== WALK-FORWARD =====")
for i, wf in enumerate(wf_results, 1):
    print(f"\nJanela {i}")
    print("Treino:", wf['train_metrics'])
    print("Teste:", wf['test_metrics'])
