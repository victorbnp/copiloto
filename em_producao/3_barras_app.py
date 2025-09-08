import MetaTrader5 as mt5
import pandas as pd
from random import randrange
import time
import psycopg2
from psycopg2 import sql
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional



# Inicializa conexão com MT5
if not mt5.initialize():
    print("Erro ao inicializar MT5")
    quit()

### Variáveis de inicialização ###    
# Nome do setup
setup = '3 barras'
# Símbolo do ativo que vai operar
simbolo = "WINV25"  
# Timeframe a ser usado, pode ser alterado para M5, M15, H1 etc.
timeframe = mt5.TIMEFRAME_M30
# Número de velas para carregar
num_barras = 5
# Número de contratos a ser usado para operar
num_contratos = 1
# Horário para encerrar as negociações
hora_fim_operacoes = 18
# Horário da barra negociada
hora_entrada_operacao = None
# Grava se o horário de encerrar o dia foi alcançado
encerrar_dia = False 
#Valor de stop de carteira
valor_stop_carteira = 2000


def atualizar_operacao_saida(
    ticket: int,
    setup: str,
    dt_saida: datetime,
    preco_saida: Decimal,
    resultado_bruto: Decimal,
    operacao_encerrada: bool = True
) -> bool:
    try:
        # Conexão com o banco de dados
        conn = psycopg2.connect(
            dbname="algo_trading",
            user="postgres",
            password="vbnp8491V",
            host="127.0.0.1",
            port="5432"
        )
        cur = conn.cursor()

        # Comando SQL de atualização
        update_query = """
        UPDATE public.tb_operacoes
        SET 
            dt_data_hora_saida = %s,
            fl_preco_saida = %s,
            fl_resultado_bruto = %s,
            bl_operacao_encerrada = %s
        WHERE 
            nr_ticket = %s AND 
            tx_setup = %s
        """

        cur.execute(update_query, (
            dt_saida,
            preco_saida,
            resultado_bruto,
            operacao_encerrada,
            ticket,
            setup
        ))
        
        if cur.rowcount == 0:
            print("Nenhum registro encontrado para atualizar.")
            return False

        conn.commit()
        print("Atualização realizada com sucesso.")
        return True

    except Exception as e:
        print(f"Erro ao atualizar dados: {e}")
        return False

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def buscar_data_hora_entrada(ticket: int, setup: str) -> Optional[datetime]:
    try:
        # Conexão com o banco de dados
        conn = psycopg2.connect(
            dbname="algo_trading",
            user="postgres",
            password="vbnp8491V",
            host="127.0.0.1",
            port="5432"
        )
        cur = conn.cursor()

        # Consulta SQL
        query = """
        SELECT dt_data_hora_entrada
        FROM public.tb_operacoes
        WHERE nr_ticket = %s AND tx_setup = %s
        LIMIT 1
        """

        cur.execute(query, (ticket, setup))
        resultado = cur.fetchone()

        if resultado:
            return resultado[0]  # datetime
        else:
            print("Nenhum registro encontrado.")
            return None

    except Exception as e:
        print(f"Erro na consulta: {e}")
        return None

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def inserir_operacao(
    dt_entrada: datetime,
    preco_entrada: Decimal,
    simbolo: str,
    timeframe: str,
    setup: str,
    quantidade: int,
    tipo_ordem: str,
    ticket: int,
    operacao_encerrada: bool = False,
    dt_saida: Optional[datetime] = None,
    preco_saida: Optional[Decimal] = None,
    resultado_bruto: Optional[Decimal] = None    
):
    try:
        # Conexão com o banco de dados
        conn = psycopg2.connect(
            dbname="algo_trading",
            user="postgres",
            password="vbnp8491V",
            host="127.0.0.1",
            port="5432"
        )
        cur = conn.cursor()

        # Comando SQL de inserção
        insert_query = """
        INSERT INTO public.tb_operacoes (
            dt_data_hora_entrada,
            dt_data_hora_saida,
            fl_preco_entrada,
            fl_preco_saida,
            tx_simbolo,
            tx_timeframe,
            fl_resultado_bruto,
            tx_setup,
            nr_quantidade_contratos,
            ch_tipo_ordem,
            bl_operacao_encerrada,
            nr_ticket
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        valores = (
            dt_entrada,
            dt_saida,
            preco_entrada,
            preco_saida,
            simbolo,
            timeframe,
            resultado_bruto,
            setup,
            quantidade,
            tipo_ordem.upper()[0],  # Garante 'C' ou 'V'
            operacao_encerrada,
            ticket
        )

        cur.execute(insert_query, valores)
        conn.commit()
        print("Inserção realizada com sucesso.")

    except Exception as e:
        print(f"Erro ao inserir dados: {e}")

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

#Função para abrir ordem a mercado
def coloca_ordem_mercado(type,symbol,position_length):
    if (type == 'buy'):
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(position_length),
            "type": mt5.ORDER_TYPE_BUY,
            "deviation": 20,
            "magic": randrange(1000000),
            "comment": "python script open",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }    
        result = mt5.order_send(request)
        print('')
    else:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(position_length),
            "type": mt5.ORDER_TYPE_SELL,
            "deviation": 20,
            "magic": randrange(1000000),
            "comment": "python script open",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }
        result = mt5.order_send(request)
    return result

# Sai de todas as posições abertas
def encerra_todas_posicoes(symbol):
    resultPositions = mt5.positions_get()

    if len(resultPositions) > 0:
        if resultPositions[0].type == 0:
            return coloca_ordem_mercado('sell',symbol,resultPositions[0].volume)
        elif resultPositions[0].type == 1:
            return coloca_ordem_mercado('buy',symbol,resultPositions[0].volume)

def mercado_aberto(symbol):
    tick = mt5.symbol_info_tick(symbol)
    if tick is not None:
        tick_time = datetime.fromtimestamp(tick.time)
        tick_time = tick_time + timedelta(hours=3)
        now = datetime.now()
        diff = (now - tick_time).total_seconds()

        if diff < 3:  # Último tick tem menos de 1 minuto
            #Mercado provavelmente está ABERTO.
            return True
        else:
            #Mercado provavelmente está FECHADO.
            return False
    else:
        return False

while not encerrar_dia:
    if not mercado_aberto(simbolo):
        continue
    #Consulta dados da conta
    account_info=mt5.account_info()

    #Teste para sair das operações por hora de fim de dia ou stop financeiro
    if (datetime.now().hour >= hora_fim_operacoes) or (account_info.equity <= valor_stop_carteira):
        encerrar_dia = True


    # Carrega dados do mercado
    rates = mt5.copy_rates_from_pos(simbolo, timeframe, 0, num_barras)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    #remover barras de leilão
    df = df[~((df['open'] == df['high']) & 
          (df['open'] == df['low']) & 
          (df['open'] == df['close']))]

    # Identifica se cada barra é compradora ou vendedora
    df['barra_compradora'] = df['close'] > df['open']
    df['barra_vendedora'] = df['close'] < df['open']

    # Conta sequências de 3 barras consecutivas
    df['barra_compradora_count'] = df['barra_compradora'][:-1].rolling(window=3).sum() == 3
    df['barra_vendedora_count'] = df['barra_vendedora'][:-1].rolling(window=3).sum() == 3

    # Marca se deve comprar, vender ou nada a fazer
    deve_comprar = df['barra_compradora_count'].iloc[-2]
    deve_vender = df['barra_vendedora_count'].iloc[-2]

    #Consulta posições abertas
    posicoes = mt5.positions_get(symbol=simbolo)
    if (not posicoes):
        #Abre uma posição caso não tenha uma aberta
        if deve_comprar:
            try:
                #Guardar a hora de entrada da operacao
                hora_entrada_operacao = df["time"].iloc[-1]
                #Abre operaçao no mercado
                retorno = coloca_ordem_mercado('buy',simbolo,num_contratos)
                #Insere operação no banco de dados
                inserir_operacao(
                    dt_entrada=hora_entrada_operacao,
                    dt_saida=None,
                    preco_entrada=retorno.price,
                    preco_saida=None,
                    simbolo=simbolo,
                    timeframe=timeframe,
                    resultado_bruto=None,
                    setup=setup,
                    quantidade=num_contratos,
                    tipo_ordem="C",
                    operacao_encerrada=False,
                    ticket=retorno.order
                )
            except Exception as e:
                print(f"Erro ao abrir posiçao: {e}")                
        elif deve_vender:
            try:
                #Guardar a hora de entrada da operacao
                hora_entrada_operacao = df["time"].iloc[-1]
                #Abre operaçao no mercado
                retorno = coloca_ordem_mercado('sell',simbolo,num_contratos)
                #Insere operação no banco de dados
                inserir_operacao(
                    dt_entrada=hora_entrada_operacao,
                    dt_saida=None,
                    preco_entrada=retorno.price,
                    preco_saida=None,
                    simbolo=simbolo,
                    timeframe=timeframe,
                    resultado_bruto=None,
                    setup=setup,
                    quantidade=num_contratos,
                    tipo_ordem="V",
                    operacao_encerrada=False,
                    ticket=retorno.order
                )
            except Exception as e:
                print(f"Erro ao abrir posiçao: {e}")  

        #print(' ')
    else:
        hora_entrada_operacao = buscar_data_hora_entrada(posicoes[0].ticket,setup)
        hora_ultima_barra = df["time"].iloc[-1]

        if posicoes[0].type == 0 and deve_vender and hora_entrada_operacao < hora_ultima_barra:
            try:
                retorno = encerra_todas_posicoes(simbolo)
                atualizar_operacao_saida(
                    ticket=posicoes[0].ticket,
                    setup=setup,
                    dt_saida=hora_ultima_barra,
                    preco_saida=retorno.price,
                    resultado_bruto=posicoes[0].profit,
                    operacao_encerrada=True
                    )
            except Exception as e:
                print(f"Erro ao abrir posiçao: {e}") 
            print('saiu compra: ', hora_ultima_barra)
        elif posicoes[0].type == 1 and deve_comprar and hora_entrada_operacao < hora_ultima_barra:
            try:
                retorno = encerra_todas_posicoes(simbolo)
                atualizar_operacao_saida(
                    ticket=posicoes[0].ticket,
                    setup=setup,
                    dt_saida=hora_ultima_barra,
                    preco_saida=retorno.price,
                    resultado_bruto=posicoes[0].profit,
                    operacao_encerrada=True
                    )
            except Exception as e:
                print(f"Erro ao abrir posiçao: {e}") 
            print('saiu venda: ', hora_ultima_barra)
        elif encerrar_dia:
            try:
                retorno = encerra_todas_posicoes(simbolo)
                atualizar_operacao_saida(
                    ticket=posicoes[0].ticket,
                    setup=setup,
                    dt_saida=hora_ultima_barra,
                    preco_saida=retorno.price,
                    resultado_bruto=posicoes[0].profit,
                    operacao_encerrada=True
                    )
            except Exception as e:
                print(f"Erro ao abrir posiçao: {e}")             
    #print(' ')
    time.sleep(1)