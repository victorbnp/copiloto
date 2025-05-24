import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, time, timedelta
import pytz
import tkinter as tk
from random import randrange
import argparse
import time

# === Argumentos de linha de comando ===
parser = argparse.ArgumentParser(description="Monitor de risco dinâmico no MetaTrader 5")
parser.add_argument('--symbol', type=str, default='WINM25', help='Símbolo do ativo (ex: WINM25, WDOU2)')
parser.add_argument('--risco', type=float, default=50.0, help='Risco máximo por operação em reais')
parser.add_argument('--parciais', type=int, choices=[2, 3], default=2, help='Quantidade de saídas parciais (2 ou 3)')
args = parser.parse_args()

# === Função para abrir ordem a mercado ===
def put_order(type,symbol,position_length):
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
        mt5.order_send(request)
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
        mt5.order_send(request)

def leave_position(symbol):
    resultPositions = mt5.positions_get()

    if len(resultPositions) > 0:
        if resultPositions[0].type == 0:
            put_order('sell',symbol,resultPositions[0].volume)
        elif resultPositions[0].type == 1:
            put_order('buy',symbol,resultPositions[0].volume)

# === Função auxiliar: maior múltiplo de 3 ===
def maior_multiplo_de_3_ate(quantidade):
    return (quantidade // 3) * 3

# === Lógica principal: coleta dados e retorna info formatada ===
def obter_dados(symbol, risco_maximo_reais):
    try:
        timezone = pytz.timezone('America/Sao_Paulo')

        now = datetime.now() - timedelta(hours=3)
        now_15 =  now - timedelta(minutes=15)

        #N_TICKS = 10000000
        #ticks = mt5.copy_ticks_from(symbol, datetime.now(timezone), N_TICKS, mt5.COPY_TICKS_ALL)

        ticks = mt5.copy_ticks_range(symbol, now_15, now, mt5.COPY_TICKS_ALL)            

        if ticks is None or len(ticks) == 0:
            return {}

        df_ticks = pd.DataFrame(ticks)
        df_ticks['time'] = pd.to_datetime(df_ticks['time'], unit='s')
        df_ticks.set_index('time', inplace=True)

        # Gera candles de 30 segundos # mudei para 2 minutos
        df_30s = df_ticks['bid'].resample('120s').agg(['first', 'max', 'min', 'last'])
        df_30s.columns = ['open', 'high', 'low', 'close']
        df_30s.reset_index(inplace=True)

        if len(df_30s) < 3:
            return {}

        # Pega as 3 últimas barras fechadas
        ultimas_barras = df_30s.iloc[-3::].copy()
        ultimas_barras['amplitude'] = ultimas_barras['high'] - ultimas_barras['low']

        # Seleciona a barra com maior amplitude
        barra_mais_volatil = ultimas_barras.loc[ultimas_barras['amplitude'].idxmax()]
        amplitude_maxima = barra_mais_volatil['amplitude']
        risco_base = amplitude_maxima / 1.7  # Metade da amplitude máxima

        # Preço atual
        preco_atual = df_ticks['bid'].iloc[-1]

        valor_por_ponto = 0.20

        # Risco por operação
        risco_compra_reais = risco_venda_reais = risco_base * valor_por_ponto

        # Quantidade de contratos
        qtd_compra = int(risco_maximo_reais // risco_compra_reais) if risco_compra_reais > 0 else 0
        qtd_venda = int(risco_maximo_reais // risco_venda_reais) if risco_venda_reais > 0 else 0

        qtd_compra_valida = maior_multiplo_de_3_ate(qtd_compra)
        qtd_venda_valida = maior_multiplo_de_3_ate(qtd_venda)

        resultado = {
            "preco": f"{preco_atual:.2f}",
            "risco_base": f"{risco_base:.2f}",
            "risco_compra_reais": f"{risco_compra_reais:.2f}",
            "risco_venda_reais": f"{risco_venda_reais:.2f}",
            "qtd_compra": qtd_compra,
            "qtd_venda": qtd_venda,
            "qtd_compra_valida": qtd_compra_valida,
            "qtd_venda_valida": qtd_venda_valida,
            "preco_valor": preco_atual
        }

        return resultado

    except Exception as e:
        print(f"Erro ao obter dados: {e}")
        return {}

# === INTERFACE GRÁFICA COM TKINTER ===
class App(tk.Tk):
    def __init__(self, symbol, risco_maximo_reais, parciais):
        super().__init__()
        self.title(f"📊 {symbol} Risk Monitor")
        self.geometry("750x180")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="black")

        # Posicionamento
        screen_width = self.winfo_screenwidth()
        window_width = 400
        offset_right = 940
        x_position = screen_width - window_width - offset_right
        self.geometry(f"+{x_position}+20")

        # Labels
        self.label_preco = tk.Label(self, text="Preço Atual: --", font=("Courier", 12), bg="black", fg="white")
        self.label_preco.pack(pady=5)

        self.label_risco = tk.Label(self, text="Risco Base: -- | R$ --", font=("Courier", 10), bg="black", fg="white")
        self.label_risco.pack(pady=2)

        self.label_qtd = tk.Label(self, text="Compra: -- → -- | Venda: -- → --", font=("Courier", 10), bg="black", fg="white")
        self.label_qtd.pack(pady=2)

        self.label_info = tk.Label(self, text="1,7 da maior amplitude das últimas 3 barras",
                                  font=("Courier", 8), bg="black", fg="gray")
        self.label_info.pack(pady=2)

        self.label_stop = tk.Label(self, text="", font=("Courier", 10), bg="black", fg="yellow")
        self.label_stop.pack(pady=5)

        self.btn_fechar = tk.Button(self, text="X", command=self.destroy, bg="red", fg="white", width=2)
        self.btn_fechar.place(x=720, y=5)

        # Variáveis para detecção de posição
        self.posicao_ativa = False
        self.tipo_posicao = None
        self.stop_loss = None
        self.risco_pts = None
        self.preco_entrada = None
        self.symbol = symbol
        self.risco_maximo_reais = risco_maximo_reais
        self.saiu_parcela = False
        self.num_parcela = 0
        self.alvo = None
        self.quantidade_total = 0
        self.parciais = parciais
        self.volume_sair = 0

        self.atualizando = False
        self.atualizar_interface()

    def atualizar_interface(self):
        if self.atualizando:
            # Já está rodando, pula esta iteração
            # self.after(300, self.atualizar_interface)
            return

        self.atualizando = True  # Marca que começou a executar


        dados = obter_dados(self.symbol, self.risco_maximo_reais)

        if not dados:
            #self.after(300, self.atualizar_interface)
            return

        # Atualiza interface
        self.label_preco.config(text=f"🎯 Preço Atual: {dados['preco']}")
        self.label_risco.config(
            text=f"📏 Risco Base: {dados['risco_base']} pts | R$ {dados['risco_compra_reais']}"
        )
        self.label_qtd.config(
            text=f"🟢 Compra: {dados['qtd_compra']:2d} → {dados['qtd_compra_valida']:2d} | "
                 f"🔴 Venda: {dados['qtd_venda']:2d} → {dados['qtd_venda_valida']:2d}"
        )

        # Verificar posição ativa
        posicoes = mt5.positions_get(symbol=self.symbol)
        if posicoes and len(posicoes) > 0:
            posicao = posicoes[0]
            tipo = "buy" if posicao.type == mt5.ORDER_TYPE_BUY else "sell"
            preco_abertura = posicao.price_open
            tamanho_lucro = 1.0  # ajuste conforme sua estratégia

            if not self.posicao_ativa:
                self.tipo_posicao = tipo
                self.preco_entrada = preco_abertura
                if self.num_parcela == 0:
                    self.risco_pts = float(dados['risco_base'])  # pontos
                self.stop_loss = preco_abertura - self.risco_pts if tipo == "buy" else preco_abertura + self.risco_pts

                self.quantidade_total = posicao.volume
                #calculando primeiro alvo da operação
                self.alvo = preco_abertura + (self.risco_pts * 2)  if tipo == "buy" else preco_abertura - (self.risco_pts * 2)

                self.posicao_ativa = True

                #Configura parciais
                self.volume_sair = self.quantidade_total / 3 if self.parciais == 3 else self.quantidade_total / 2

                self.label_stop.config(
                    text=f"🟠 Operação Ativa: {'COMPRA' if tipo == 'buy' else 'VENDA'} | "
                         f"Stop: {self.stop_loss:.2f} | Alvo: {preco_abertura + tamanho_lucro * self.risco_pts:.2f}",
                    fg="orange"
                )
            else:
                preco_atual = dados["preco_valor"]

                #print(args.parciais)

                # Verifica se atingiu o stop
                if self.tipo_posicao == "buy" and preco_atual <= self.stop_loss:
                    self.label_stop.config(text="🛑 STOP ATINGIDO (COMPRA)!", fg="red")
                    leave_position(self.symbol)
                elif self.tipo_posicao == "sell" and preco_atual >= self.stop_loss:
                    self.label_stop.config(text="🛑 STOP ATINGIDO (VENDA)!", fg="red")
                    leave_position(self.symbol)
                else:
                ####                 
                    if self.tipo_posicao == "buy" and preco_atual >= self.alvo:
                        self.num_parcela = self.num_parcela + 1
                        if self.num_parcela == parciais:
                            leave_position(self.symbol)
                            self.volume_sair = self.quantidade_total
                        else:                                
                            
                            put_order('sell', self.symbol, self.volume_sair)
                            self.quantidade_total = self.quantidade_total - self.volume_sair
                        self.label_stop.config(
                            text=f"🟡 Fechou {self.volume_sair:.0f} contratos | Alvo: {self.alvo:.2f}", fg="yellow")
                        self.stop_loss = self.preco_entrada
                        self.alvo = self.alvo + (self.risco_pts)

                    elif self.tipo_posicao == "sell" and preco_atual <= self.alvo:
                        self.num_parcela = self.num_parcela + 1
                        if self.num_parcela == parciais:
                            leave_position(self.symbol)
                            self.volume_sair = self.quantidade_total
                        else:                         
                            put_order('buy', self.symbol, self.volume_sair)
                            self.quantidade_total = self.quantidade_total - self.volume_sair
                        self.label_stop.config(
                            text=f"🟡 Fechou {self.volume_sair:.0f} contratos | Alvo: {self.alvo:.2f}", fg="yellow")
                        self.stop_loss = self.preco_entrada
                        self.alvo = self.alvo - (self.risco_pts)

                    elif self.num_parcela > 0:
                        self.label_stop.config(
                            text=f"✔️ Parcial {self.num_parcela:.2f} realizada | Alvo: {self.alvo:.2f} | Stop: {self.stop_loss:.2f} ", fg="lightgreen")

                    else:
                        self.label_stop.config(
                            text=f"🟢 Ativa desde: {self.preco_entrada} | Alvo: {self.alvo:.2f} | Stop: {self.stop_loss:.2f}", fg="lightgreen")
                    ####
                    #self.label_stop.config(
                     #   text=f"🟢 Ativa desde: {self.preco_entrada:.2f} | Alvo: {self.alvo:.2f} | Stop: {self.stop_loss:.2f}", fg="lightgreen"
                    #)

        else:
            if self.posicao_ativa:
                self.label_stop.config(text="✔️ Sem posição ativa", fg="gray")
                self.posicao_ativa = False
                self.num_parcela = 0
                self.volume_sair = 0
            else:
                self.label_stop.config(text="🔍 Aguardando posição ativa...", fg="gray")
        
        self.atualizando = False
        #self.after(300, self.atualizar_interface)

# === INICIALIZAÇÃO DO APLICATIVO ===
if __name__ == "__main__":
    symbol = args.symbol
    risco_maximo_reais = args.risco
    parciais = args.parciais
    rodou = True
    if not mt5.initialize():
        print("❌ Falha ao inicializar o MT5")
    else:
        app = App(symbol, risco_maximo_reais, parciais)
        #app.mainloop()
        while rodou:
            rodou = False
            app.atualizar_interface()
            #app.update_idletasks()
            app.update()
            time.sleep(0.3)
            rodou = True
        mt5.shutdown()