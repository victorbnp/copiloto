import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import Optional, Tuple

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configurações ajustáveis
SYMBOL = "WINM25"          # Ativo desejado
RISK_REAIS = 100.0         # Risco em reais por operação
POSITION_TYPE = "sell"     # "buy" ou "sell"
VALOR_POR_PONTO = 0.2      # Valor por ponto do ativo
NUM_VELAS_ANALISE = 3      # Número de velas para análise
INTERVALO_CONSULTA = 5     # Intervalo entre consultas em segundos
TIMEFRAME_SECONDS = 30     # Timeframe em segundos para as velas

def initialize_mt5() -> bool:
    """Inicializa a conexão com o MetaTrader 5."""
    if not mt5.initialize():
        logger.error("Falha ao conectar ao MetaTrader 5")
        return False
    logger.info("Conexão com MT5 estabelecida com sucesso")
    return True

def get_ohlc_data(symbol: str, num_bars: int = 10) -> Optional[pd.DataFrame]:
    """
    Obtém dados OHLC agrupados em intervalos personalizados com múltiplas estratégias de fallback.
    """
    now = datetime.now()
    start_time = now - timedelta(seconds=TIMEFRAME_SECONDS * num_bars * 3)  # Janela ampliada
    
    try:
        # Tentativa 1: Obter ticks com COPY_TICKS_ALL
        ticks = mt5.copy_ticks_range(symbol, start_time, now, mt5.COPY_TICKS_ALL)
        
        # Fallback 1: Tentar COPY_TICKS_TRADE se ALL falhar
        if ticks is None or len(ticks) == 0:
            ticks = mt5.copy_ticks_range(symbol, start_time, now, mt5.COPY_TICKS_TRADE)
            logger.debug("Usando fallback COPY_TICKS_TRADE")
        
        # Fallback 2: Tentar rates se ticks falharem
        if ticks is None or len(ticks) == 0:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, num_bars * 3)
            if rates is not None and len(rates) > 0:
                logger.debug("Usando fallback de rates M1")
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                df['price'] = (df['high'] + df['low']) / 2
                return df
            
            # Fallback 3: Tentar último tick conhecido
            last_tick = mt5.symbol_info_tick(symbol)
            if last_tick is not None:
                logger.debug("Usando último tick disponível")
                df = pd.DataFrame([{
                    'time': pd.to_datetime(last_tick.time, unit='s'),
                    'price': (last_tick.bid + last_tick.ask) / 2
                }])
                return df
            
            raise ValueError("Não foi possível obter dados do ativo")
        
        # Processamento normal dos ticks
        df = pd.DataFrame(ticks)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df['price'] = (df['bid'] + df['ask']) / 2

        # Agrupamento temporal
        df['group'] = (df['time'].astype('int64') // (TIMEFRAME_SECONDS * 1_000_000_000))
        
        ohlc = df.groupby('group').agg(
            open=('price', 'first'),
            high=('price', 'max'),
            low=('price', 'min'),
            close=('price', 'last'),
            time=('time', 'first')
        ).sort_values('time').reset_index(drop=True)
        
        return ohlc.iloc[-num_bars:] if len(ohlc) >= num_bars else ohlc
        
    except Exception as e:
        logger.error(f"Falha ao obter dados: {str(e)}")
        return None

def calculate_position(ohlc_data: pd.DataFrame, position_type: str, num_bars: int = 1) -> Optional[Tuple[float, float, int]]:
    """
    Calcula os parâmetros da posição com base no risco.
    
    Args:
        ohlc_data: DataFrame com dados OHLC
        position_type: Tipo de posição ('buy' ou 'sell')
        num_bars: Número de velas para análise
    
    Returns:
        Tuple (stop_price, distance_points, contracts) ou None em caso de erro
    """
    if ohlc_data is None or len(ohlc_data) < num_bars + 1:
        logger.warning("Dados insuficientes para cálculo")
        return None
    
    try:
        current_price = ohlc_data.iloc[-1]['close']
        
        if position_type == 'sell':
            stop = ohlc_data.iloc[-num_bars-1:-1]['high'].max()
            dist = max(stop - current_price, 0.01)
        else:
            stop = ohlc_data.iloc[-num_bars-1:-1]['low'].min()
            dist = max(current_price - stop, 0.01)
        
        contracts = int(RISK_REAIS / (dist * VALOR_POR_PONTO))
        
        return stop, dist, contracts
        
    except Exception as e:
        logger.error(f"Erro no cálculo da posição: {str(e)}")
        return None

def main_loop():
    """Loop principal de análise e tomada de decisão."""
    if not initialize_mt5():
        return
    
    logger.info(f"Iniciando monitoramento do ativo {SYMBOL}")
    logger.info(f"Configuração: Risco={RISK_REAIS} BRL | Tipo={POSITION_TYPE}")
    
    try:
        while True:
            start_time = time.time()
            
            # Obtém dados
            df = get_ohlc_data(SYMBOL, NUM_VELAS_ANALISE + 1)
            
            if df is not None and len(df) >= NUM_VELAS_ANALISE + 1:
                current_price = df.iloc[-1]['close']
                logger.info(f"\nPreço atual: {current_price:.2f}")
                
                # Analisa múltiplos cenários
                for i in range(1, NUM_VELAS_ANALISE + 1):
                    result = calculate_position(df, POSITION_TYPE, i)
                    if result:
                        stop, dist, contracts = result
                        logger.info(
                            f"[{i} vela(s)] Stop: {stop:.2f} | "
                            f"Distância: {dist:.2f} pts | "
                            f"Contratos: {contracts}"
                        )
            
            # Controle do intervalo entre consultas
            elapsed = time.time() - start_time
            sleep_time = max(INTERVALO_CONSULTA - elapsed, 0)
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Encerrando o bot por solicitação do usuário")
    finally:
        mt5.shutdown()
        logger.info("Conexão com MT5 encerrada")

if __name__ == "__main__":
    main_loop()