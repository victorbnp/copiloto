import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import pytz
import tkinter as tk

# === Função auxiliar: maior múltiplo de 3 ===
def maior_multiplo_de_3_ate(quantidade):
    return (quantidade // 3) * 3

# === Lógica principal: coleta dados e retorna info formatada ===
def obter_dados():
    try:
        timezone = pytz.timezone('America/Sao_Paulo')
        date1 = datetime(datetime.now().year, datetime.now().month, datetime.now().day, tzinfo=timezone)

        N_TICKS = 10000000
        ticks = mt5.copy_ticks_from("WINM25", date1, N_TICKS, mt5.COPY_TICKS_ALL)

        if ticks is None or len(ticks) == 0:
            return {}

        df_ticks = pd.DataFrame(ticks)
        df_ticks['time'] = pd.to_datetime(df_ticks['time'], unit='s')
        df_ticks.set_index('time', inplace=True)

        df_30s = df_ticks['bid'].resample('30s').agg(['first', 'max', 'min', 'last'])
        df_30s.columns = ['open', 'high', 'low', 'close']
        df_30s.reset_index(inplace=True)

        preco_atual = df_ticks['bid'].iloc[-1]

        risco_maximo_reais = 100.0
        valor_por_ponto = 0.20

        resultado = {"preco": f"{preco_atual:.2f}", "dados": []}

        for n in [1, 2, 3, 4]:
            ultimas_barras = df_30s.tail(n)
            lowest_low = ultimas_barras['low'].min()
            highest_high = ultimas_barras['high'].max()

            risco_compra = abs(preco_atual - lowest_low) * valor_por_ponto
            risco_venda = abs(highest_high - preco_atual) * valor_por_ponto

            qtd_compra = int(risco_maximo_reais // risco_compra) if risco_compra > 0 else 0
            qtd_venda = int(risco_maximo_reais // risco_venda) if risco_venda > 0 else 0

            qtd_compra_valida = maior_multiplo_de_3_ate(qtd_compra)
            qtd_venda_valida = maior_multiplo_de_3_ate(qtd_venda)

            resultado["dados"].append({
                "n": n,
                "risco_compra": f"{risco_compra:.2f}",
                "qtd_compra": qtd_compra,
                "qtd_compra_valida": qtd_compra_valida,
                "risco_venda": f"{risco_venda:.2f}",
                "qtd_venda": qtd_venda,
                "qtd_venda_valida": qtd_venda_valida,
            })

        return resultado

    except Exception as e:
        print(f"Erro ao obter dados: {e}")
        return {}

# === INTERFACE GRÁFICA COM TKINTER ===
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("📊 WINM25 Risk Monitor")
        self.geometry("300x200")
        self.overrideredirect(True)  # Remove bordas da janela
        self.attributes("-topmost", True)  # Mantém no topo
        self.configure(bg="black")

        # Posicionar à direita da tela, sem ficar em cima do gráfico
        screen_width = self.winfo_screenwidth()
        window_width = 300
        offset_right = 600 #2200  # Ajuste esse valor para mover mais ou menos pra esquerda/direita

        x_position = screen_width - window_width - offset_right
        self.geometry(f"+{x_position}+50")  # Ajuste a altura Y conforme necessário

        # Label do preço atual
        self.label_preco = tk.Label(self, text="Preço Atual: --", font=("Courier", 12), bg="black", fg="white")
        self.label_preco.pack(pady=5)

        # Labels das barras
        self.labels = []
        for i in range(4):
            frame = tk.Frame(self, bg="black")
            frame.pack(anchor="w", padx=10)

            label = tk.Label(frame, text=f"Barra {i+1}: --", font=("Courier", 10), width=30, anchor="w", bg="black", fg="white")
            label.pack(side="left")
            self.labels.append(label)

        # Botão de fechar (X)
        btn = tk.Button(self, text="X", command=self.destroy, bg="red", fg="white", width=2)
        btn.place(x=270, y=5)

        # Iniciar atualização automática
        self.atualizar_interface()

    def atualizar_interface(self):
        dados = obter_dados()

        if not dados:
            self.after(1000, self.atualizar_interface)
            return

        self.label_preco.config(text=f"🎯 Preço Atual: {dados['preco']}")

        for i, info in enumerate(dados.get("dados", [])):
            texto = (
                f"🔴{info['n']}→ "
                f"C: {info['qtd_compra']:2d} → {info['qtd_compra_valida']:2d} | "
                f"V: {info['qtd_venda']:2d} → {info['qtd_venda_valida']:2d}"
            )
            self.labels[i].config(text=texto)

        self.after(500, self.atualizar_interface)

# === INICIALIZAÇÃO DO APLICATIVO ===
if __name__ == "__main__":
    if not mt5.initialize():
        print("❌ Falha ao inicializar o MT5")
    else:
        app = App()
        app.mainloop()
        mt5.shutdown()