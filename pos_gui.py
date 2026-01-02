# pos_gui.py (TOUCH FRIENDLY)
import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from pos_core import (
    InventarioDB, POSService, money_from_cents,
    MAX_CUENTAS, LOW_STOCK_THRESHOLD, app_base_dir
)

# -----------------------------
# Helpers OS (abrir / imprimir)
# -----------------------------
def open_path_in_os(path: str):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform.startswith("darwin"):
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except Exception:
        pass


def print_path_in_os(path: str) -> None:
    """
    Imprime un archivo usando impresora predeterminada.
    - Windows: verbo "print"
    - macOS/Linux: lpr
    """
    if not path:
        raise RuntimeError("Ruta vacía.")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe: {path}")

    try:
        if sys.platform.startswith("win"):
            os.startfile(path, "print")  # type: ignore[attr-defined]
        else:
            subprocess.run(["lpr", path], check=True)
    except Exception as e:
        raise RuntimeError(f"No se pudo imprimir. Detalle: {e}")


# -----------------------------
# Estilo táctil (colores/fonts)
# -----------------------------
PALETTE = {
    "bg": "#0E1117",
    "panel": "#161B22",
    "text": "#E6EDF3",
    "muted": "#9BA3AF",
    "primary": "#1F6FEB",
    "success": "#2EA043",
    "warning": "#D29922",
    "danger": "#F85149",
    "btn": "#30363D",
    "btn2": "#21262D",
    "border": "#30363D"
}

FONT_BASE = ("Segoe UI", 14)
FONT_BIG = ("Segoe UI", 16, "bold")
FONT_HUGE = ("Segoe UI", 18, "bold")


# -----------------------------
# Dialogs
# -----------------------------
class LoginDialog(tk.Toplevel):
    def __init__(self, parent, service: POSService):
        super().__init__(parent)
        self.title("Login - POS")
        self.resizable(False, False)
        self.configure(bg=PALETTE["panel"])
        self.service = service
        self.result = None  # (username, role)

        frm = tk.Frame(self, bg=PALETTE["panel"], padx=16, pady=16)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="Usuario", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_BIG).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.ent_user = tk.Entry(frm, width=22, font=FONT_BIG)
        self.ent_user.grid(row=0, column=1, sticky="w", pady=(0, 6))

        tk.Label(frm, text="Contraseña", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_BIG).grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.ent_pass = tk.Entry(frm, width=22, show="*", font=FONT_BIG)
        self.ent_pass.grid(row=1, column=1, sticky="w", pady=(0, 6))

        tk.Label(
            frm,
            text="Default:\nadmin / admin123\ncajero / cajero123",
            fg=PALETTE["muted"],
            bg=PALETTE["panel"],
            font=("Segoe UI", 12)
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 12))

        btns = tk.Frame(frm, bg=PALETTE["panel"])
        btns.grid(row=3, column=0, columnspan=2, sticky="e")

        def big_btn(parent, text, cmd, color):
            return tk.Button(
                parent, text=text, command=cmd,
                font=FONT_BIG, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, padx=18, pady=10, cursor="hand2"
            )

        big_btn(btns, "Salir", self._cancel, PALETTE["danger"]).pack(side="right", padx=8)
        big_btn(btns, "Entrar", self._login, PALETTE["primary"]).pack(side="right")

        self.bind("<Return>", lambda e: self._login())
        self.bind("<Escape>", lambda e: self._cancel())

        self.transient(parent)
                # --- Forzar visible / centrado (Windows-friendly) ---
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

        # Levantar y forzar focus (evita que quede detrás)
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))

        self.grab_set()
        self.ent_user.focus_set()

    def _login(self):
        u = self.ent_user.get().strip()
        p = self.ent_pass.get().strip()
        ok, role = self.service.authenticate(u, p)
        if not ok:
            messagebox.showerror("Login", "Usuario o contraseña incorrectos.", parent=self)
            return
        self.result = (u.lower(), role)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class ProductEditor(tk.Toplevel):
    def __init__(self, parent, title: str, initial: dict | None = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=PALETTE["panel"])
        self.result = None

        initial = initial or {"nombre": "", "tipo": "bebida", "precio": 0.0, "stock": 0}

        frm = tk.Frame(self, bg=PALETTE["panel"], padx=16, pady=16)
        frm.pack(fill="both", expand=True)

        def lbl(t, r):
            tk.Label(frm, text=t, fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_BIG).grid(row=r, column=0, sticky="w", pady=8)

        lbl("Nombre:", 0)
        self.ent_nombre = tk.Entry(frm, width=32, font=FONT_BIG)
        self.ent_nombre.grid(row=0, column=1, sticky="w", pady=8)
        self.ent_nombre.insert(0, initial["nombre"])

        lbl("Tipo:", 1)
        self.cb_tipo = ttk.Combobox(frm, state="readonly", values=["bebida", "comida"], width=14, font=FONT_BIG)
        self.cb_tipo.grid(row=1, column=1, sticky="w", pady=8)
        self.cb_tipo.set(initial["tipo"])

        lbl("Precio (colones):", 2)
        self.ent_precio = tk.Entry(frm, width=14, font=FONT_BIG)
        self.ent_precio.grid(row=2, column=1, sticky="w", pady=8)
        self.ent_precio.insert(0, str(initial["precio"]))

        lbl("Stock:", 3)
        self.ent_stock = tk.Entry(frm, width=14, font=FONT_BIG)
        self.ent_stock.grid(row=3, column=1, sticky="w", pady=8)
        self.ent_stock.insert(0, str(initial["stock"]))

        btns = tk.Frame(frm, bg=PALETTE["panel"])
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))

        def big_btn(text, cmd, color):
            return tk.Button(
                btns, text=text, command=cmd,
                font=FONT_BIG, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, padx=18, pady=10, cursor="hand2"
            )

        big_btn("Cancelar", self._cancel, PALETTE["danger"]).pack(side="right", padx=8)
        big_btn("Guardar", self._save, PALETTE["success"]).pack(side="right")

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self._cancel())

        self.transient(parent)
        self.grab_set()
        self.ent_nombre.focus_set()

    def _save(self):
        nombre = self.ent_nombre.get().strip()
        tipo = self.cb_tipo.get().strip().lower()

        try:
            precio = float(self.ent_precio.get().strip().replace(",", "."))
        except ValueError:
            messagebox.showerror("Error", "Precio inválido.", parent=self)
            return

        try:
            stock = int(self.ent_stock.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Stock inválido (entero).", parent=self)
            return

        if not nombre:
            messagebox.showerror("Error", "El nombre no puede estar vacío.", parent=self)
            return
        if tipo not in ("bebida", "comida"):
            messagebox.showerror("Error", "Tipo inválido.", parent=self)
            return
        if precio < 0 or stock < 0:
            messagebox.showerror("Error", "Precio/Stock inválidos.", parent=self)
            return

        self.result = {"nombre": nombre, "tipo": tipo, "precio": precio, "stock": stock}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class UsersManager(tk.Toplevel):
    def __init__(self, parent, service: POSService):
        super().__init__(parent)
        self.title("Usuarios (Admin)")
        self.geometry("720x480")
        self.configure(bg=PALETTE["bg"])
        self.service = service

        top = tk.Frame(self, bg=PALETTE["panel"], padx=12, pady=12)
        top.pack(fill="x")

        tk.Label(top, text="Gestión de usuarios", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_HUGE).pack(side="left")

        def btn(text, cmd, color):
            return tk.Button(top, text=text, command=cmd, font=FONT_BIG, fg="white", bg=color,
                             bd=0, padx=14, pady=10, cursor="hand2",
                             activebackground=color, activeforeground="white")

        btn("Nuevo", self.new_user, PALETTE["primary"]).pack(side="right", padx=6)
        btn("Reset Pass", self.reset_pass, PALETTE["warning"]).pack(side="right", padx=6)
        btn("Eliminar", self.delete_user, PALETTE["danger"]).pack(side="right", padx=6)
        btn("Refrescar", self.refresh, PALETTE["btn"]).pack(side="right", padx=6)

        mid = tk.Frame(self, bg=PALETTE["bg"], padx=12, pady=12)
        mid.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("Treeview", rowheight=34, font=FONT_BASE)
        style.configure("Treeview.Heading", font=("Segoe UI", 13, "bold"))

        self.tv = ttk.Treeview(mid, columns=("user", "role", "created"), show="headings", height=10)
        self.tv.heading("user", text="Usuario")
        self.tv.heading("role", text="Rol")
        self.tv.heading("created", text="Creado")
        self.tv.column("user", width=180)
        self.tv.column("role", width=120, anchor="center")
        self.tv.column("created", width=280)
        self.tv.pack(fill="both", expand=True)

        self.refresh()

    def refresh(self):
        for i in self.tv.get_children():
            self.tv.delete(i)
        for r in self.service.list_users():
            self.tv.insert("", "end", values=(r["username"], r["role"], r["created_ts"]))

    def _selected_user(self):
        sel = self.tv.selection()
        if not sel:
            return None
        vals = self.tv.item(sel[0], "values")
        return vals[0]

    def new_user(self):
        u = simpledialog.askstring("Nuevo usuario", "Usuario:", parent=self)
        if not u:
            return
        role = simpledialog.askstring("Nuevo usuario", "Rol (admin/cajero):", parent=self)
        if not role:
            return
        p = simpledialog.askstring("Nuevo usuario", "Contraseña:", parent=self, show="*")
        if not p:
            return
        try:
            self.service.create_user(u, p, role)
            messagebox.showinfo("OK", "Usuario creado.", parent=self)
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def reset_pass(self):
        u = self._selected_user()
        if not u:
            messagebox.showinfo("Reset", "Selecciona un usuario.", parent=self)
            return
        p = simpledialog.askstring("Reset password", f"Nueva contraseña para {u}:", parent=self, show="*")
        if not p:
            return
        try:
            self.service.set_password(u, p)
            messagebox.showinfo("OK", "Contraseña actualizada.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def delete_user(self):
        u = self._selected_user()
        if not u:
            messagebox.showinfo("Eliminar", "Selecciona un usuario.", parent=self)
            return
        if not messagebox.askyesno("Confirmar", f"¿Eliminar usuario {u}?", parent=self):
            return
        try:
            self.service.delete_user(u)
            messagebox.showinfo("OK", "Usuario eliminado.", parent=self)
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)


class CashOpenDialog(tk.Toplevel):
    """Dialog táctil para apertura de caja."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Apertura de Caja")
        self.resizable(False, False)
        self.configure(bg=PALETTE["panel"])
        self.result = None  # monto en colones (float)

        frm = tk.Frame(self, bg=PALETTE["panel"], padx=20, pady=20)
        frm.pack(fill="both", expand=True)

        tk.Label(
            frm,
            text="Monto inicial en caja (colones):",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_BIG
        ).pack(pady=(0, 10))

        self.entry = tk.Entry(frm, width=15, font=FONT_HUGE, justify="center")
        self.entry.pack(pady=(0, 20), ipady=8)
        self.entry.insert(0, "20000")
        self.entry.select_range(0, tk.END)

        btns = tk.Frame(frm, bg=PALETTE["panel"])
        btns.pack()

        def big_btn(text, cmd, color):
            return tk.Button(
                btns, text=text, command=cmd,
                font=FONT_BIG, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, padx=24, pady=12, cursor="hand2"
            )

        big_btn("Cancelar", self._cancel, PALETTE["danger"]).pack(side="left", padx=8)
        big_btn("Abrir Caja", self._confirm, PALETTE["success"]).pack(side="left", padx=8)

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self._cancel())

        self.transient(parent)
        self.grab_set()
        self.entry.focus_set()
        self._center()

    def _center(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _confirm(self):
        try:
            amount = float(self.entry.get().strip().replace(",", ""))
            if amount < 0:
                raise ValueError()
            self.result = amount
            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Ingresa un monto válido.", parent=self)

    def _cancel(self):
        self.result = None
        self.destroy()


class PaymentMethodDialog(tk.Toplevel):
    """Dialog táctil para seleccionar método de pago."""
    def __init__(self, parent, total_centavos: int):
        super().__init__(parent)
        self.title("Método de Pago")
        self.resizable(False, False)
        self.configure(bg=PALETTE["panel"])
        self.total_centavos = total_centavos
        self.result = None  # {"method": str, "cash_received": int, "change": int}

        frm = tk.Frame(self, bg=PALETTE["panel"], padx=20, pady=20)
        frm.pack(fill="both", expand=True)

        from pos_core import money_from_cents
        total_str = money_from_cents(total_centavos)

        tk.Label(
            frm,
            text=f"Total a pagar: {total_str}",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_HUGE
        ).pack(pady=(0, 20))

        tk.Label(
            frm,
            text="Selecciona método de pago:",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_BIG
        ).pack(pady=(0, 10))

        btns = tk.Frame(frm, bg=PALETTE["panel"])
        btns.pack(pady=(0, 10))

        def method_btn(text, method, color):
            return tk.Button(
                btns, text=text,
                command=lambda: self._select_method(method),
                font=FONT_BIG, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, width=12, height=2, cursor="hand2"
            )

        method_btn("💵 EFECTIVO", "EFECTIVO", PALETTE["success"]).pack(side="left", padx=8)
        method_btn("💳 TARJETA", "TARJETA", PALETTE["primary"]).pack(side="left", padx=8)
        method_btn("📱 SINPE", "SINPE", PALETTE["warning"]).pack(side="left", padx=8)

        tk.Button(
            frm, text="Cancelar",
            command=self._cancel,
            font=FONT_BASE, fg="white", bg=PALETTE["danger"],
            activebackground=PALETTE["danger"], activeforeground="white",
            bd=0, padx=18, pady=10, cursor="hand2"
        ).pack(pady=(10, 0))

        self.transient(parent)
        self.grab_set()
        self._center()

    def _center(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _select_method(self, method):
        if method == "EFECTIVO":
            self._handle_cash_payment()
        else:
            # TARJETA o SINPE: sin recibido/vuelto
            self.result = {
                "method": method,
                "cash_received": None,
                "change": None
            }
            self.destroy()

    def _handle_cash_payment(self):
        """Sub-dialog para pago en efectivo con keypad."""
        cash_dlg = CashPaymentDialog(self, self.total_centavos)
        self.wait_window(cash_dlg)
        if cash_dlg.result:
            self.result = cash_dlg.result
            self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class CashPaymentDialog(tk.Toplevel):
    """Dialog para ingresar monto recibido en efectivo con keypad."""
    def __init__(self, parent, total_centavos: int):
        super().__init__(parent)
        self.title("Pago en Efectivo")
        self.resizable(False, False)
        self.configure(bg=PALETTE["panel"])
        self.total_centavos = total_centavos
        self.result = None

        from pos_core import money_from_cents
        self.total_colones = total_centavos / 100

        frm = tk.Frame(self, bg=PALETTE["panel"], padx=20, pady=20)
        frm.pack(fill="both", expand=True)

        tk.Label(
            frm,
            text=f"Total: {money_from_cents(total_centavos)}",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_BIG
        ).pack(pady=(0, 10))

        tk.Label(
            frm,
            text="Monto recibido:",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_BIG
        ).pack()

        self.received_var = tk.StringVar(value=str(int(self.total_colones)))
        self.entry = tk.Entry(
            frm,
            textvariable=self.received_var,
            font=("Segoe UI", 20, "bold"),
            width=12,
            justify="center",
            state="readonly",
            readonlybackground="white"
        )
        self.entry.pack(pady=(0, 10), ipady=8)

        # Vuelto
        self.lbl_change = tk.Label(
            frm,
            text="Vuelto: ₡0.00",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_HUGE
        )
        self.lbl_change.pack(pady=(0, 10))

        # Keypad
        keypad = tk.Frame(frm, bg=PALETTE["panel"])
        keypad.pack(pady=(0, 10))

        keypad_buttons = [
            ['7', '8', '9'],
            ['4', '5', '6'],
            ['1', '2', '3'],
            ['C', '0', '←']
        ]

        for row_idx, row in enumerate(keypad_buttons):
            for col_idx, char in enumerate(row):
                btn = tk.Button(
                    keypad,
                    text=char,
                    command=lambda c=char: self._keypad_press(c),
                    font=FONT_BIG,
                    fg="white",
                    bg=PALETTE["btn2"] if char in ['C', '←'] else PALETTE["primary"],
                    activebackground=PALETTE["btn2"] if char in ['C', '←'] else PALETTE["primary"],
                    activeforeground="white",
                    bd=0,
                    width=4,
                    height=2,
                    cursor="hand2"
                )
                btn.grid(row=row_idx, column=col_idx, padx=3, pady=3)

        # Botones
        btns_frame = tk.Frame(frm, bg=PALETTE["panel"])
        btns_frame.pack()

        def big_btn(text, cmd, color):
            return tk.Button(
                btns_frame, text=text, command=cmd,
                font=FONT_BIG, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, padx=20, pady=12, cursor="hand2"
            )

        big_btn("Cancelar", self._cancel, PALETTE["danger"]).pack(side="left", padx=8)
        big_btn("Confirmar", self._confirm, PALETTE["success"]).pack(side="left", padx=8)

        self.transient(parent)
        self.grab_set()
        self._center()
        self._update_change()

    def _center(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _keypad_press(self, char):
        current = self.received_var.get()

        if char == 'C':
            self.received_var.set(str(int(self.total_colones)))
        elif char == '←':
            if len(current) > 1:
                self.received_var.set(current[:-1])
            else:
                self.received_var.set("0")
        else:
            if current == "0":
                self.received_var.set(char)
            else:
                if len(current) < 8:
                    self.received_var.set(current + char)

        self._update_change()

    def _update_change(self):
        try:
            received = int(self.received_var.get())
            change = received - self.total_colones
            if change >= 0:
                self.lbl_change.config(text=f"Vuelto: ₡{change:,.2f}", fg=PALETTE["success"])
            else:
                self.lbl_change.config(text=f"FALTA: ₡{abs(change):,.2f}", fg=PALETTE["danger"])
        except ValueError:
            self.lbl_change.config(text="Vuelto: ₡0.00", fg=PALETTE["text"])

    def _confirm(self):
        try:
            received_colones = int(self.received_var.get())
            if received_colones < self.total_colones:
                messagebox.showerror("Error", "El monto recibido es menor al total.", parent=self)
                return

            received_centavos = int(received_colones * 100)
            change_centavos = received_centavos - self.total_centavos

            self.result = {
                "method": "EFECTIVO",
                "cash_received": received_centavos,
                "change": change_centavos
            }
            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Monto inválido.", parent=self)

    def _cancel(self):
        self.result = None
        self.destroy()


class CashCloseDialog(tk.Toplevel):
    """Dialog táctil para cierre de caja."""
    def __init__(self, parent, expected_cash_colones: float):
        super().__init__(parent)
        self.title("Cierre de Caja")
        self.resizable(False, False)
        self.configure(bg=PALETTE["panel"])
        self.expected_cash_colones = expected_cash_colones
        self.result = None  # {"counted": float, "notes": str}

        frm = tk.Frame(self, bg=PALETTE["panel"], padx=20, pady=20)
        frm.pack(fill="both", expand=True)

        tk.Label(
            frm,
            text=f"Efectivo esperado: ₡{expected_cash_colones:,.2f}",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_BIG
        ).pack(pady=(0, 15))

        tk.Label(
            frm,
            text="Efectivo contado en caja:",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_BIG
        ).pack()

        self.entry_counted = tk.Entry(frm, width=15, font=FONT_HUGE, justify="center")
        self.entry_counted.pack(pady=(0, 10), ipady=8)
        self.entry_counted.insert(0, str(int(expected_cash_colones)))
        self.entry_counted.bind("<KeyRelease>", self._update_diff)

        self.lbl_diff = tk.Label(
            frm,
            text="Diferencia: ₡0.00",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_HUGE
        )
        self.lbl_diff.pack(pady=(0, 15))

        tk.Label(
            frm,
            text="Notas (opcional):",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_BASE
        ).pack()

        self.entry_notes = tk.Entry(frm, width=40, font=FONT_BASE)
        self.entry_notes.pack(pady=(0, 20))

        btns = tk.Frame(frm, bg=PALETTE["panel"])
        btns.pack()

        def big_btn(text, cmd, color):
            return tk.Button(
                btns, text=text, command=cmd,
                font=FONT_BIG, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, padx=24, pady=12, cursor="hand2"
            )

        big_btn("Cancelar", self._cancel, PALETTE["danger"]).pack(side="left", padx=8)
        big_btn("Cerrar Caja", self._confirm, PALETTE["success"]).pack(side="left", padx=8)

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self._cancel())

        self.transient(parent)
        self.grab_set()
        self.entry_counted.focus_set()
        self.entry_counted.select_range(0, tk.END)
        self._center()

    def _center(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _update_diff(self, event=None):
        try:
            counted = float(self.entry_counted.get().strip().replace(",", ""))
            diff = counted - self.expected_cash_colones
            color = PALETTE["success"] if diff >= 0 else PALETTE["danger"]
            self.lbl_diff.config(text=f"Diferencia: ₡{diff:,.2f}", fg=color)
        except ValueError:
            self.lbl_diff.config(text="Diferencia: --", fg=PALETTE["text"])

    def _confirm(self):
        try:
            counted = float(self.entry_counted.get().strip().replace(",", ""))
            if counted < 0:
                raise ValueError()
            notes = self.entry_notes.get().strip()
            self.result = {"counted": counted, "notes": notes}
            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Ingresa un monto válido.", parent=self)

    def _cancel(self):
        self.result = None
        self.destroy()


class ProductCatalog(tk.Frame):
    """
    Catálogo táctil de productos con tabs por categoría (Bebidas/Comidas).
    Muestra productos como tiles (botones grandes) en un grid scrollable.
    """
    def __init__(self, parent, on_product_click_callback, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg=PALETTE["bg"])
        self.on_product_click_callback = on_product_click_callback
        self.catalog_buttons = {}  # pid -> button widget
        
        # Notebook para categorías
        self.cat_notebook = ttk.Notebook(self)
        self.cat_notebook.pack(fill="both", expand=True)
        
        # Frame para Bebidas
        self.bebidas_frame = tk.Frame(self.cat_notebook, bg=PALETTE["bg"])
        self.cat_notebook.add(self.bebidas_frame, text="🍺 Bebidas")
        
        # Frame para Comidas
        self.comidas_frame = tk.Frame(self.cat_notebook, bg=PALETTE["bg"])
        self.cat_notebook.add(self.comidas_frame, text="🍔 Comidas")
        
        # Crear canvas scrollable para cada categoría
        self.bebidas_scroll = self._create_scrollable_grid(self.bebidas_frame)
        self.comidas_scroll = self._create_scrollable_grid(self.comidas_frame)
    
    def _create_scrollable_grid(self, parent):
        """Crea un canvas con scrollbar vertical para mostrar el grid de productos."""
        # Frame contenedor
        container = tk.Frame(parent, bg=PALETTE["bg"])
        container.pack(fill="both", expand=True)
        
        # Canvas
        canvas = tk.Canvas(container, bg=PALETTE["bg"], highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        
        # Scrollbar
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Frame interno donde van los botones
        inner_frame = tk.Frame(canvas, bg=PALETTE["bg"])
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        
        # Actualizar región scrollable cuando cambia el tamaño
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        
        inner_frame.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        
        # Soporte para scroll con rueda del mouse
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        return inner_frame
    
    def build_catalog(self, products_list, search_filter=""):
        """
        Construye el catálogo completo desde cero.
        products_list: lista de objetos Producto.
        search_filter: texto para filtrar productos por nombre (case-insensitive).
        """
        # Limpiar botones existentes
        self.catalog_buttons.clear()
        
        # Limpiar widgets existentes en los frames
        for widget in self.bebidas_scroll.winfo_children():
            widget.destroy()
        for widget in self.comidas_scroll.winfo_children():
            widget.destroy()
        
        # Aplicar filtro de búsqueda si existe
        if search_filter:
            search_lower = search_filter.lower()
            products_list = [p for p in products_list if search_lower in p.nombre.lower()]
        
        # Separar productos por categoría
        bebidas = [p for p in products_list if p.tipo == "bebida"]
        comidas = [p for p in products_list if p.tipo == "comida"]
        
        # Construir grids
        self._build_product_grid(self.bebidas_scroll, bebidas)
        self._build_product_grid(self.comidas_scroll, comidas)
    
    def _build_product_grid(self, parent_frame, products):
        """Construye el grid de productos en 3 columnas."""
        if not products:
            tk.Label(
                parent_frame,
                text="No hay productos en esta categoría",
                fg=PALETTE["muted"],
                bg=PALETTE["bg"],
                font=FONT_BIG
            ).pack(pady=40)
            return
        
        # Grid de 3 columnas
        cols = 3
        row = 0
        col = 0
        
        for prod in products:
            btn = self._create_product_tile(parent_frame, prod)
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
            self.catalog_buttons[prod.id] = btn
            
            col += 1
            if col >= cols:
                col = 0
                row += 1
        
        # Configurar columnas para que se expandan uniformemente
        for c in range(cols):
            parent_frame.grid_columnconfigure(c, weight=1, uniform="cols")
    
    def _create_product_tile(self, parent, prod):
        """Crea un botón tile para un producto."""
        # Determinar color según stock
        if prod.stock <= 0:
            bg_color = PALETTE["btn2"]  # Gris
            state = "disabled"
        elif prod.stock <= LOW_STOCK_THRESHOLD:
            bg_color = PALETTE["warning"]  # Amarillo
            state = "normal"
        else:
            bg_color = PALETTE["success"]  # Verde
            state = "normal"
        
        # Texto del botón
        btn_text = f"{prod.nombre}\n{money_from_cents(prod.precio_centavos)}\nStock: {prod.stock}"
        
        btn = tk.Button(
            parent,
            text=btn_text,
            font=FONT_BASE,
            fg="white",
            bg=bg_color,
            activeforeground="white",
            activebackground=bg_color,
            bd=0,
            width=16,
            height=4,
            cursor="hand2" if state == "normal" else "arrow",
            state=state,
            wraplength=160,
            command=lambda p=prod: self.on_product_click_callback(p)
        )
        
        return btn
    
    def update_product_tile(self, product):
        """
        Actualiza un tile específico (color y texto) sin reconstruir todo.
        product: objeto Producto actualizado.
        """
        btn = self.catalog_buttons.get(product.id)
        if not btn:
            return
        
        # Determinar nuevo color y estado
        if product.stock <= 0:
            bg_color = PALETTE["btn2"]
            state = "disabled"
        elif product.stock <= LOW_STOCK_THRESHOLD:
            bg_color = PALETTE["warning"]
            state = "normal"
        else:
            bg_color = PALETTE["success"]
            state = "normal"
        
        # Actualizar texto y color
        btn_text = f"{product.nombre}\n{money_from_cents(product.precio_centavos)}\nStock: {product.stock}"
        btn.config(
            text=btn_text,
            bg=bg_color,
            activebackground=bg_color,
            state=state,
            cursor="hand2" if state == "normal" else "arrow"
        )


# -----------------------------
# App principal (Touch UI)
# -----------------------------
class POSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("POS Bar - Touch")
        self.configure(bg=PALETTE["bg"])

        # Full HD optimizado para 1920x1080
        self.geometry("1920x1080")
        self._try_zoom()

        self.db = InventarioDB()
        self.service = POSService(self.db)

        # Login
        self.user = None
        self.role = None
        self.update_idletasks()

        dlg = LoginDialog(self, self.service)
        self.wait_window(dlg)

        if dlg.result is None:
            self.destroy()
            return

        self.user, self.role = dlg.result
        self.current_user = self.user  # Alias para uso en mensajes


        # Touch helpers
        self.selected_slot = None
        self.product_map = {}
        self.qty_var = tk.IntVar(value=1)
        self.last_product_id = None  # Último producto tocado en el catálogo
        self.catalog_widget = None  # Referencia al widget ProductCatalog
        
        # Búsqueda y keypad táctil
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.on_search_change())
        self.qty_str_var = tk.StringVar(value="1")
        self.current_filter = ""  # Texto de búsqueda actual

        self._setup_ttk_style()
        self._build_ui()
        self.apply_permissions()
        self.refresh_all()

        self.after(150, self.check_stale_accounts)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Hotkeys
        self.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.bind("<Escape>", lambda e: self.exit_fullscreen())

        self._fullscreen = False

    def _try_zoom(self):
        try:
            if sys.platform.startswith("win"):
                self.state("zoomed")
        except Exception:
            pass

    def toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        try:
            self.attributes("-fullscreen", self._fullscreen)
        except Exception:
            pass

    def exit_fullscreen(self):
        self._fullscreen = False
        try:
            self.attributes("-fullscreen", False)
        except Exception:
            pass

    def _setup_ttk_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TNotebook", background=PALETTE["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 13, "bold"))
        style.configure("Treeview", rowheight=36, font=FONT_BASE)
        style.configure("Treeview.Heading", font=("Segoe UI", 13, "bold"))
        style.configure("TCombobox", font=FONT_BASE)

    # ---------------- Permisos ----------------
    def is_admin(self) -> bool:
        return self.role == "admin"

    def apply_permissions(self):
        admin = self.is_admin()
        # Inventario CRUD
        for btn in [self.btn_new_prod, self.btn_edit_prod, self.btn_adj_stock]:
            btn.config(state=("normal" if admin else "disabled"))
        # Cierre diario
        self.btn_close_day.config(state=("normal" if admin else "disabled"))
        # Usuarios
        self.btn_users.config(state=("normal" if admin else "disabled"))

    # ---------------- Cuentas viejo día ----------------
    def check_stale_accounts(self):
        stale = self.service.stale_open_accounts()
        if not stale:
            return
        today = self.service.business_date()
        msg_lines = [f"Hoy es {today}, pero hay cuentas abiertas de otro día:"]
        for slot, nombre, opened_date in stale[:8]:
            msg_lines.append(f"- Slot {slot}: {nombre} (abierta {opened_date})")
        if len(stale) > 8:
            msg_lines.append(f"... y {len(stale) - 8} más")
        msg_lines.append("\n¿Quieres mantenerlas cargadas?\n\nSí = cargar\nNo = limpiar mesas (NO borra ventas/recibos)")
        keep = messagebox.askyesno("Cuentas pendientes", "\n".join(msg_lines), parent=self)
        if not keep:
            self.service.clear_open_accounts()
            self.selected_slot = None
            self.refresh_all()

    # ---------------- UI ----------------
    def _build_ui(self):
        # Header touch
        header = tk.Frame(self, bg=PALETTE["panel"], padx=14, pady=12)
        header.pack(fill="x")

        self.lbl_day = tk.Label(header, text="Día: --", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_HUGE)
        self.lbl_day.pack(side="left")

        self.lbl_user = tk.Label(header, text=f"Usuario: {self.user} ({self.role})", fg=PALETTE["muted"], bg=PALETTE["panel"], font=FONT_BASE)
        self.lbl_user.pack(side="left", padx=18)

        def hbtn(text, cmd, color):
            return tk.Button(
                header, text=text, command=cmd,
                font=FONT_BIG, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, padx=16, pady=10, cursor="hand2"
            )

        hbtn("Refrescar", self.refresh_all, PALETTE["btn"]).pack(side="right", padx=8)
        hbtn("Exportar CSV", self.gui_export_csv_quick_today, PALETTE["primary"]).pack(side="right", padx=8)

        # Notebook
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        self.tab_cuentas = tk.Frame(self.nb, bg=PALETTE["bg"])
        self.tab_inventario = tk.Frame(self.nb, bg=PALETTE["bg"])
        self.tab_reportes = tk.Frame(self.nb, bg=PALETTE["bg"])

        self.nb.add(self.tab_cuentas, text="Cuentas")
        self.nb.add(self.tab_inventario, text="Inventario")
        self.nb.add(self.tab_reportes, text="Reportes / Recibos")

        self._build_cuentas_tab()
        self._build_inventario_tab()
        self._build_reportes_tab()

    # --------------- CUENTAS TAB (touch) ---------------
    def _build_cuentas_tab(self):
        root = self.tab_cuentas

        # Left: grid mesas
        left = tk.Frame(root, bg=PALETTE["bg"], padx=14, pady=14)
        left.pack(side="left", fill="y")

        tk.Label(left, text="Mesas / Cuentas", fg=PALETTE["text"], bg=PALETTE["bg"], font=FONT_HUGE).pack(anchor="w")

        grid = tk.Frame(left, bg=PALETTE["bg"])
        grid.pack(pady=(12, 10))

        self.account_buttons = {}  # slot -> tk.Button

        def mk_tile(slot: int):
            btn = tk.Button(
                grid,
                text=f"Mesa {slot}\nLIBRE",
                font=FONT_BIG,
                fg="white",
                bg=PALETTE["success"],
                activeforeground="white",
                activebackground=PALETTE["success"],
                bd=0,
                width=12,
                height=3,
                cursor="hand2",
                command=lambda s=slot: self.select_slot(s)
            )
            return btn

        # layout 2 columnas x 5 filas (más grande)
        r = 0
        c = 0
        for slot in range(1, MAX_CUENTAS + 1):
            btn = mk_tile(slot)
            btn.grid(row=r, column=c, padx=10, pady=10)
            self.account_buttons[slot] = btn
            c += 1
            if c == 2:
                c = 0
                r += 1

        # Quick actions (touch)
        actions = tk.Frame(left, bg=PALETTE["bg"])
        actions.pack(fill="x", pady=(10, 0))

        def big_action(text, cmd, color):
            return tk.Button(
                actions, text=text, command=cmd,
                font=FONT_BIG, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, padx=14, pady=12, cursor="hand2"
            )

        big_action("Abrir Mesa", self.gui_open_account_touch, PALETTE["primary"]).pack(fill="x", pady=6)
        big_action("Cobrar / Cerrar", self.gui_close_account, PALETTE["warning"]).pack(fill="x", pady=6)
        big_action("Liberar (vacía)", self.gui_free_empty_selected, PALETTE["btn"]).pack(fill="x", pady=6)

        # Right: CATÁLOGO + detalle
        right = tk.Frame(root, bg=PALETTE["bg"])
        right.pack(side="left", fill="both", expand=True)

        # Top: Cuenta seleccionada
        top_right = tk.Frame(right, bg=PALETTE["bg"])
        top_right.pack(fill="x", padx=14, pady=(14, 0))

        self.lbl_selected = tk.Label(top_right, text="Cuenta seleccionada: (ninguna)", fg=PALETTE["text"], bg=PALETTE["bg"], font=FONT_HUGE)
        self.lbl_selected.pack(anchor="w")

        # CATÁLOGO TÁCTIL
        catalog_container = tk.Frame(right, bg=PALETTE["panel"])
        catalog_container.pack(fill="both", expand=True, padx=10, pady=(6, 0))

        # Panel superior: búsqueda + cantidad + keypad
        top_catalog = tk.Frame(catalog_container, bg=PALETTE["panel"])
        top_catalog.pack(fill="x", padx=6, pady=(6, 6))

        # Columna izquierda: búsqueda
        left_col = tk.Frame(top_catalog, bg=PALETTE["panel"])
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(
            left_col,
            text="🔍 Buscar producto:",
            fg=PALETTE["text"],
            bg=PALETTE["panel"],
            font=FONT_BIG
        ).pack(anchor="w", pady=(0, 4))

        search_frame = tk.Frame(left_col, bg=PALETTE["panel"])
        search_frame.pack(fill="x", pady=(0, 8))

        self.search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            font=FONT_BIG,
            width=30
        )
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.search_entry.bind("<Return>", self.on_search_enter)

        tk.Button(
            search_frame,
            text="✖ Limpiar",
            command=self.clear_search,
            font=FONT_BASE,
            fg="white",
            bg=PALETTE["danger"],
            activebackground=PALETTE["danger"],
            activeforeground="white",
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2"
        ).pack(side="left", padx=(8, 0))

        # Info de búsqueda
        self.lbl_search_info = tk.Label(
            left_col,
            text="Escribe para filtrar. Enter = agregar si hay 1 resultado.",
            fg=PALETTE["muted"],
            bg=PALETTE["panel"],
            font=("Segoe UI", 11)
        )
        self.lbl_search_info.pack(anchor="w")

        # Columna derecha: cantidad + keypad
        right_col = tk.Frame(top_catalog, bg=PALETTE["btn"])
        right_col.pack(side="left", fill="y", padx=(8, 0))

        tk.Label(
            right_col,
            text="🔢 Cantidad:",
            fg=PALETTE["text"],
            bg=PALETTE["btn"],
            font=FONT_BIG
        ).pack(pady=(8, 4))

        self.qty_entry = tk.Entry(
            right_col,
            textvariable=self.qty_str_var,
            font=("Segoe UI", 18, "bold"),
            width=5,
            justify="center",
            state="readonly",
            readonlybackground="white"
        )
        self.qty_entry.pack(pady=(0, 6), padx=6)

        # Teclado numérico
        keypad = tk.Frame(right_col, bg=PALETTE["btn"])
        keypad.pack(padx=8, pady=(0, 8))

        # Botones del keypad: 3 columnas
        keypad_buttons = [
            ['7', '8', '9'],
            ['4', '5', '6'],
            ['1', '2', '3'],
            ['C', '0', '←']
        ]

        for row_idx, row in enumerate(keypad_buttons):
            for col_idx, char in enumerate(row):
                btn = tk.Button(
                    keypad,
                    text=char,
                    command=lambda c=char: self.keypad_press(c),
                    font=FONT_BASE,
                    fg="white",
                    bg=PALETTE["btn2"] if char in ['C', '←'] else PALETTE["primary"],
                    activebackground=PALETTE["btn2"] if char in ['C', '←'] else PALETTE["primary"],
                    activeforeground="white",
                    bd=0,
                    width=3,
                    height=1,
                    cursor="hand2"
                )
                btn.grid(row=row_idx, column=col_idx, padx=2, pady=2)

        # Catálogo de productos
        self.catalog_widget = ProductCatalog(catalog_container, on_product_click_callback=self.on_product_tile_click, bg=PALETTE["panel"])
        self.catalog_widget.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Panel de control rápido (último producto + botones +1/-1)
        quick_panel = tk.Frame(catalog_container, bg=PALETTE["panel"])
        quick_panel.pack(fill="x", pady=(4, 4))

        self.lbl_last_product = tk.Label(
            quick_panel,
            text="Último producto: (ninguno)",
            fg=PALETTE["muted"],
            bg=PALETTE["panel"],
            font=FONT_BASE
        )
        self.lbl_last_product.pack(side="left", padx=8)

        def quick_btn(text, cmd, color):
            return tk.Button(
                quick_panel, text=text, command=cmd,
                font=FONT_BASE, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, padx=16, pady=6, cursor="hand2"
            )

        quick_btn("-1", self.quick_remove_last, PALETTE["danger"]).pack(side="right", padx=3)
        quick_btn("+1", self.quick_add_last, PALETTE["success"]).pack(side="right", padx=3)

        # Detalle de cuenta
        detail_container = tk.Frame(right, bg=PALETTE["bg"])
        detail_container.pack(fill="both", expand=False, padx=10, pady=(6, 10))

        tk.Label(
            detail_container,
            text="📝 Detalle de la cuenta",
            fg=PALETTE["text"],
            bg=PALETTE["bg"],
            font=FONT_BIG
        ).pack(anchor="w", pady=(0, 4))

        # Items tree
        self.tv_items = ttk.Treeview(detail_container, columns=("pid", "nombre", "qty", "punit", "linea"), show="headings", height=6)
        for col, txt, w, anc in [
            ("pid", "ID", 70, "center"),
            ("nombre", "Producto", 420, "w"),
            ("qty", "Cant", 80, "center"),
            ("punit", "P.Unit", 140, "e"),
            ("linea", "Subtotal", 160, "e"),
        ]:
            self.tv_items.heading(col, text=txt)
            self.tv_items.column(col, width=w, anchor=anc)
        self.tv_items.pack(fill="both", expand=False, pady=(4, 8))

        totals = tk.Frame(detail_container, bg=PALETTE["panel"], padx=14, pady=12)
        totals.pack(fill="x")

        self.lbl_sub = tk.Label(totals, text="Subtotal: ₡0.00", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_BIG)
        self.lbl_iva = tk.Label(totals, text="IVA 13%: ₡0.00", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_BIG)
        self.lbl_tot = tk.Label(totals, text="Total: ₡0.00", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_HUGE)

        self.lbl_sub.pack(side="left", padx=12)
        self.lbl_iva.pack(side="left", padx=12)
        self.lbl_tot.pack(side="right", padx=12)

        # Controls add/remove (FALLBACK - opcional con combobox)
        controls = tk.Frame(detail_container, bg=PALETTE["panel"])
        controls.pack(fill="x", padx=14, pady=(8, 0))

        tk.Label(controls, text="Método alternativo:", fg=PALETTE["muted"], bg=PALETTE["panel"], font=("Segoe UI", 12, "italic")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        tk.Label(controls, text="Producto", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_BASE).grid(row=1, column=0, sticky="w")
        self.cb_products = ttk.Combobox(controls, width=38, state="readonly", font=FONT_BASE)
        self.cb_products.grid(row=1, column=1, padx=10, pady=8, sticky="w")

        tk.Label(controls, text="Cantidad", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_BASE).grid(row=1, column=2, sticky="w", padx=(10, 0))

        qty_frame = tk.Frame(controls, bg=PALETTE["panel"])
        qty_frame.grid(row=1, column=3, sticky="w", padx=10)

        def qty_btn(text, cmd):
            return tk.Button(
                qty_frame, text=text, command=cmd,
                font=FONT_BASE, fg="white", bg=PALETTE["btn"],
                bd=0, padx=10, pady=6, cursor="hand2"
            )

        qty_btn("−", self.qty_minus).pack(side="left", padx=4)
        self.ent_qty = tk.Entry(qty_frame, width=4, font=FONT_BASE, justify="center", textvariable=self.qty_var)
        self.ent_qty.pack(side="left")
        qty_btn("+", self.qty_plus).pack(side="left", padx=4)

        # Add/remove buttons
        btn_row = tk.Frame(controls, bg=PALETTE["panel"])
        btn_row.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        def action_btn(text, cmd, color):
            return tk.Button(
                btn_row, text=text, command=cmd,
                font=FONT_BASE, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                bd=0, padx=14, pady=8, cursor="hand2"
            )

        action_btn("Agregar", self.gui_add_item, PALETTE["success"]).pack(side="left", padx=6)
        action_btn("Quitar (seleccionado)", self.gui_remove_item, PALETTE["danger"]).pack(side="left", padx=6)

        controls.grid_columnconfigure(1, weight=1)

    def qty_minus(self):
        v = self.qty_var.get()
        if v > 1:
            self.qty_var.set(v - 1)

    def qty_plus(self):
        v = self.qty_var.get()
        if v < 9999:
            self.qty_var.set(v + 1)

    # --------------- INVENTARIO TAB ---------------
    def _build_inventario_tab(self):
        root = self.tab_inventario

        top = tk.Frame(root, bg=PALETTE["panel"], padx=14, pady=12)
        top.pack(fill="x")

        tk.Label(top, text="Inventario", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_HUGE).pack(side="left")

        def btn(text, cmd, color):
            return tk.Button(top, text=text, command=cmd, font=FONT_BIG, fg="white", bg=color,
                             bd=0, padx=14, pady=10, cursor="hand2",
                             activebackground=color, activeforeground="white")

        self.btn_new_prod = btn("Nuevo", self.gui_new_product, PALETTE["primary"])
        self.btn_edit_prod = btn("Editar", self.gui_edit_product, PALETTE["warning"])
        self.btn_adj_stock = btn("Stock", self.gui_adjust_stock, PALETTE["btn"])
        btn_refresh = btn("Refrescar", self.refresh_inventory, PALETTE["btn2"])

        btn_refresh.pack(side="right", padx=6)
        self.btn_adj_stock.pack(side="right", padx=6)
        self.btn_edit_prod.pack(side="right", padx=6)
        self.btn_new_prod.pack(side="right", padx=6)

        mid = tk.Frame(root, bg=PALETTE["bg"], padx=14, pady=14)
        mid.pack(fill="both", expand=True)

        self.tv_inv = ttk.Treeview(mid, columns=("id", "tipo", "nombre", "precio", "stock", "estado"), show="headings", height=14)
        for col, txt, w, anc in [
            ("id", "ID", 60, "center"),
            ("tipo", "Tipo", 90, "center"),
            ("nombre", "Producto", 420, "w"),
            ("precio", "Precio", 140, "e"),
            ("stock", "Stock", 90, "center"),
            ("estado", "Estado", 120, "center"),
        ]:
            self.tv_inv.heading(col, text=txt)
            self.tv_inv.column(col, width=w, anchor=anc)
        self.tv_inv.pack(fill="both", expand=True)

        tk.Label(root, text="Solo ADMIN puede modificar inventario.", fg=PALETTE["muted"], bg=PALETTE["bg"], font=FONT_BASE).pack(anchor="w", padx=14, pady=(0, 10))

    # --------------- REPORTES TAB ---------------
    def _build_reportes_tab(self):
        root = self.tab_reportes

        top = tk.Frame(root, bg=PALETTE["panel"], padx=14, pady=12)
        top.pack(fill="x")

        tk.Label(top, text="Fecha (YYYY-MM-DD):", fg=PALETTE["text"], bg=PALETTE["panel"], font=FONT_BIG).pack(side="left")
        self.ent_report_date = tk.Entry(top, width=12, font=FONT_BIG)
        self.ent_report_date.pack(side="left", padx=10)

        def btn(text, cmd, color):
            return tk.Button(top, text=text, command=cmd, font=FONT_BIG, fg="white", bg=color,
                             bd=0, padx=14, pady=10, cursor="hand2",
                             activebackground=color, activeforeground="white")

        btn("Cargar", self.load_report, PALETTE["btn"]).pack(side="left", padx=8)
        btn("Exportar CSV", self.gui_export_csv, PALETTE["primary"]).pack(side="left", padx=8)

        self.btn_users = btn("Usuarios", self.gui_users, PALETTE["warning"])
        self.btn_users.pack(side="left", padx=8)

        # Botones de caja
        self.btn_cash_open = btn("🔓 Apertura Caja", self.gui_cash_open, PALETTE["success"])
        self.btn_cash_open.pack(side="right", padx=8)

        self.btn_cash_close = btn("🔒 Cierre Caja", self.gui_cash_close, PALETTE["danger"])
        self.btn_cash_close.pack(side="right", padx=8)

        self.btn_cash_report = btn("💰 Reporte Caja", self.gui_cash_report, PALETTE["primary"])
        self.btn_cash_report.pack(side="right", padx=8)

        self.btn_close_day = btn("Cierre Diario (hoy)", self.gui_close_day, PALETTE["danger"])
        self.btn_close_day.pack(side="right", padx=8)

        # Status de caja
        cash_status_frame = tk.Frame(root, bg=PALETTE["bg"], padx=14, pady=10)
        cash_status_frame.pack(fill="x")
        
        self.lbl_cash_status = tk.Label(
            cash_status_frame,
            text="Estado de caja: Cargando...",
            fg=PALETTE["text"],
            bg=PALETTE["bg"],
            font=FONT_BIG
        )
        self.lbl_cash_status.pack(anchor="w")

        summary = tk.Frame(root, bg=PALETTE["bg"], padx=14, pady=14)
        summary.pack(fill="x")

        self.lbl_rep_cnt = tk.Label(summary, text="Cuentas cerradas: 0", fg=PALETTE["text"], bg=PALETTE["bg"], font=FONT_BIG)
        self.lbl_rep_sub = tk.Label(summary, text="Subtotal: ₡0.00", fg=PALETTE["text"], bg=PALETTE["bg"], font=FONT_BIG)
        self.lbl_rep_iva = tk.Label(summary, text="IVA: ₡0.00", fg=PALETTE["text"], bg=PALETTE["bg"], font=FONT_BIG)
        self.lbl_rep_tot = tk.Label(summary, text="Total: ₡0.00", fg=PALETTE["text"], bg=PALETTE["bg"], font=FONT_HUGE)

        self.lbl_rep_cnt.pack(side="left", padx=10)
        self.lbl_rep_sub.pack(side="left", padx=10)
        self.lbl_rep_iva.pack(side="left", padx=10)
        self.lbl_rep_tot.pack(side="right", padx=10)

        mid = tk.Frame(root, bg=PALETTE["bg"], padx=14, pady=14)
        mid.pack(fill="both", expand=True)

        left = tk.Frame(mid, bg=PALETTE["bg"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        tk.Label(left, text="Ventas por producto", fg=PALETTE["text"], bg=PALETTE["bg"], font=FONT_HUGE).pack(anchor="w")
        self.tv_sales = ttk.Treeview(left, columns=("nombre", "tipo", "qty", "total"), show="headings", height=10)
        for col, txt, w, anc in [
            ("nombre", "Producto", 320, "w"),
            ("tipo", "Tipo", 90, "center"),
            ("qty", "Cantidad", 100, "center"),
            ("total", "Total", 160, "e"),
        ]:
            self.tv_sales.heading(col, text=txt)
            self.tv_sales.column(col, width=w, anchor=anc)
        self.tv_sales.pack(fill="both", expand=True, pady=(10, 0))

        right = tk.Frame(mid, bg=PALETTE["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        tk.Label(right, text="Recibos (reimprimir)", fg=PALETTE["text"], bg=PALETTE["bg"], font=FONT_HUGE).pack(anchor="w")

        self.tv_receipts = ttk.Treeview(right, columns=("no", "cuenta", "ts", "pdf"), show="headings", height=10)
        self.tv_receipts.heading("no", text="#")
        self.tv_receipts.heading("cuenta", text="Cuenta")
        self.tv_receipts.heading("ts", text="Hora")
        self.tv_receipts.heading("pdf", text="Archivo")
        self.tv_receipts.column("no", width=60, anchor="center")
        self.tv_receipts.column("cuenta", width=220, anchor="w")
        self.tv_receipts.column("ts", width=90, anchor="center")
        self.tv_receipts.column("pdf", width=220, anchor="w")
        self.tv_receipts.pack(fill="both", expand=True, pady=(10, 10))

        btns = tk.Frame(right, bg=PALETTE["bg"])
        btns.pack(fill="x")

        def rbtn(text, cmd, color):
            return tk.Button(btns, text=text, command=cmd, font=FONT_BIG, fg="white", bg=color,
                             bd=0, padx=12, pady=10, cursor="hand2",
                             activebackground=color, activeforeground="white")

        rbtn("Abrir PDF", self.gui_open_receipt_pdf, PALETTE["btn"]).pack(side="left", padx=6)
        rbtn("Imprimir PDF", self.gui_print_receipt_pdf, PALETTE["primary"]).pack(side="left", padx=6)
        rbtn("Abrir TXT", self.gui_open_receipt_txt, PALETTE["btn"]).pack(side="left", padx=6)
        rbtn("Imprimir TXT", self.gui_print_receipt_txt, PALETTE["success"]).pack(side="left", padx=6)
        rbtn("Carpeta", self.gui_open_receipts_folder, PALETTE["btn2"]).pack(side="left", padx=6)

    # ---------------- Catálogo táctil ----------------
    def on_product_tile_click(self, product):
        """Callback cuando se toca un producto del catálogo."""
        # Validar que haya cuenta seleccionada
        if self.selected_slot is None:
            messagebox.showwarning(
                "Sin cuenta",
                "Selecciona y abre una mesa primero antes de agregar productos.",
                parent=self
            )
            return
        
        if self.service.cuentas.get(self.selected_slot) is None:
            messagebox.showwarning(
                "Mesa libre",
                f"La Mesa {self.selected_slot} está libre. Ábrela primero con el botón 'Abrir Mesa'.",
                parent=self
            )
            return
        
        # Obtener cantidad del keypad
        try:
            qty = int(self.qty_str_var.get())
            if qty < 1:
                qty = 1
        except ValueError:
            qty = 1
        
        # Agregar cantidad especificada del producto
        try:
            self.service.add_item(self.selected_slot, product.id, qty)
            self.last_product_id = product.id
            self.lbl_last_product.config(text=f"Último producto: {product.nombre}")
            
            # Mantener cantidad para agregar varias veces (Opción A)
            # Si prefieres resetear a 1, descomenta la siguiente línea:
            # self.qty_str_var.set("1")
            
            # Refresh completo
            self.refresh_inventory()
            self.refresh_products_combobox()
            self.refresh_account_detail()
            self.refresh_accounts_tiles()
            self.refresh_catalog()
        except Exception as e:
            messagebox.showerror("Error al agregar", str(e), parent=self)
    
    def quick_add_last(self):
        """Agrega 1 unidad más del último producto tocado."""
        if self.last_product_id is None:
            messagebox.showinfo("Sin producto", "No has seleccionado ningún producto del catálogo aún.", parent=self)
            return
        
        if self.selected_slot is None or self.service.cuentas.get(self.selected_slot) is None:
            messagebox.showwarning(
                "Sin cuenta",
                "Selecciona y abre una mesa primero.",
                parent=self
            )
            return
        
        try:
            prod = self.service.get_product(self.last_product_id)
            if not prod:
                messagebox.showerror("Error", "El producto ya no existe.", parent=self)
                return
            
            self.service.add_item(self.selected_slot, self.last_product_id, 1)
            
            # Refresh
            self.refresh_inventory()
            self.refresh_products_combobox()
            self.refresh_account_detail()
            self.refresh_accounts_tiles()
            self.refresh_catalog()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
    
    def quick_remove_last(self):
        """Quita 1 unidad del último producto tocado."""
        if self.last_product_id is None:
            messagebox.showinfo("Sin producto", "No has seleccionado ningún producto del catálogo aún.", parent=self)
            return
        
        if self.selected_slot is None or self.service.cuentas.get(self.selected_slot) is None:
            messagebox.showwarning(
                "Sin cuenta",
                "Selecciona y abre una mesa primero.",
                parent=self
            )
            return
        
        try:
            self.service.remove_item(self.selected_slot, self.last_product_id, 1)
            
            # Refresh
            self.refresh_inventory()
            self.refresh_products_combobox()
            self.refresh_account_detail()
            self.refresh_accounts_tiles()
            self.refresh_catalog()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
    
    # ---------------- Teclado numérico y búsqueda ----------------
    def keypad_press(self, char):
        """Maneja la pulsación de teclas del keypad numérico."""
        current = self.qty_str_var.get()
        
        if char == 'C':
            # Clear: resetear a 1
            self.qty_str_var.set("1")
        elif char == '←':
            # Backspace: borrar último dígito
            if len(current) > 1:
                self.qty_str_var.set(current[:-1])
            else:
                self.qty_str_var.set("1")
        else:
            # Número: agregar dígito
            if current == "1" and len(current) == 1:
                # Si es el default "1", reemplazar
                self.qty_str_var.set(char)
            else:
                # Agregar dígito (máximo 4 dígitos)
                if len(current) < 4:
                    self.qty_str_var.set(current + char)
    
    def on_search_change(self):
        """Se llama cuando cambia el texto de búsqueda."""
        search_text = self.search_var.get().strip()
        self.current_filter = search_text
        self.refresh_catalog()
    
    def clear_search(self):
        """Limpia el campo de búsqueda."""
        self.search_var.set("")
        self.search_entry.focus_set()
    
    def on_search_enter(self, event=None):
        """Enter en búsqueda: si hay exactamente 1 resultado, agregarlo."""
        if self.selected_slot is None or self.service.cuentas.get(self.selected_slot) is None:
            messagebox.showwarning(
                "Sin cuenta",
                "Abre una mesa primero.",
                parent=self
            )
            return
        
        # Obtener productos filtrados
        search_text = self.search_var.get().strip()
        if not search_text:
            return
        
        products = self.service.list_products()
        search_lower = search_text.lower()
        filtered = [p for p in products if search_lower in p.nombre.lower()]
        
        if len(filtered) == 1:
            # Exactamente 1 resultado: agregarlo
            product = filtered[0]
            try:
                qty = int(self.qty_str_var.get())
                if qty < 1:
                    qty = 1
            except ValueError:
                qty = 1
            
            try:
                self.service.add_item(self.selected_slot, product.id, qty)
                self.last_product_id = product.id
                self.lbl_last_product.config(text=f"Último producto: {product.nombre}")
                
                # Limpiar búsqueda y resetear cantidad
                self.search_var.set("")
                # Opcional: resetear cantidad a 1
                # self.qty_str_var.set("1")
                
                # Refresh
                self.refresh_inventory()
                self.refresh_products_combobox()
                self.refresh_account_detail()
                self.refresh_accounts_tiles()
                self.refresh_catalog()
                
                messagebox.showinfo(
                    "Agregado",
                    f"Se agregaron {qty}x {product.nombre}",
                    parent=self
                )
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)
        elif len(filtered) == 0:
            messagebox.showinfo(
                "Sin resultados",
                f"No se encontraron productos con '{search_text}'.",
                parent=self
            )
        else:
            messagebox.showinfo(
                "Múltiples resultados",
                f"Se encontraron {len(filtered)} productos. Refina tu búsqueda o toca el producto deseado.",
                parent=self
            )
    
    def refresh_catalog(self):
        """Refresca el catálogo de productos (reconstrucción completa)."""
        if self.catalog_widget is None:
            return
        
        products = self.service.list_products()
        # Aplicar filtro de búsqueda actual
        self.catalog_widget.build_catalog(products, self.current_filter)


    # ---------------- Refresh ----------------
    def refresh_all(self):
        bd = self.service.business_date()
        self.lbl_day.config(text=f"Día: {bd}")

        self.ent_report_date.delete(0, tk.END)
        self.ent_report_date.insert(0, bd)

        self.refresh_accounts_tiles()
        self.refresh_inventory()
        self.refresh_products_combobox()
        self.refresh_account_detail()
        self.refresh_catalog()
        self.load_report()
        self.update_cash_status()

    def refresh_accounts_tiles(self):
        # Actualiza textos/colores de las 10 mesas
        for st in self.service.accounts_state():
            slot = st["slot"]
            btn = self.account_buttons.get(slot)
            if not btn:
                continue

            if st["estado"] == "LIBRE":
                btn.configure(
                    text=f"Mesa {slot}\nLIBRE",
                    bg=PALETTE["success"],
                    activebackground=PALETTE["success"]
                )
            elif st["estado"] == "VACIA":
                name = st["nombre"] or f"Mesa {slot}"
                btn.configure(
                    text=f"{name}\nVACÍA",
                    bg=PALETTE["warning"],
                    activebackground=PALETTE["warning"]
                )
            else:
                name = st["nombre"] or f"Mesa {slot}"
                btn.configure(
                    text=f"{name}\nOCUPADA ({st['items']})",
                    bg=PALETTE["danger"],
                    activebackground=PALETTE["danger"]
                )

            # Resalta seleccionada con borde “simulado” usando relieve
            if self.selected_slot == slot:
                btn.configure(relief="sunken")
            else:
                btn.configure(relief="flat")

        if self.selected_slot is not None:
            if self.service.cuentas.get(self.selected_slot) is None:
                self.selected_slot = None
                self.lbl_selected.config(text="Cuenta seleccionada: (ninguna)")
                self.clear_items_view()

    def refresh_products_combobox(self):
        self.product_map.clear()
        products = self.service.list_products()
        items = []
        for p in products:
            text = f"{p.id} - {p.nombre} ({p.tipo}) | {money_from_cents(p.precio_centavos)} | Stock: {p.stock}"
            items.append(text)
            self.product_map[text] = p.id
        self.cb_products["values"] = items
        if items:
            self.cb_products.current(0)

    def refresh_inventory(self):
        for i in self.tv_inv.get_children():
            self.tv_inv.delete(i)

        products = self.service.list_products()
        for p in products:
            if p.stock <= 0:
                estado = "SIN STOCK"
            elif p.stock <= LOW_STOCK_THRESHOLD:
                estado = "BAJO"
            else:
                estado = "OK"
            self.tv_inv.insert("", "end", values=(p.id, p.tipo, p.nombre, money_from_cents(p.precio_centavos), p.stock, estado))

    def clear_items_view(self):
        for i in self.tv_items.get_children():
            self.tv_items.delete(i)
        self.lbl_sub.config(text="Subtotal: ₡0.00")
        self.lbl_iva.config(text="IVA 13%: ₡0.00")
        self.lbl_tot.config(text="Total: ₡0.00")

    def refresh_account_detail(self):
        if self.selected_slot is None:
            self.lbl_selected.config(text="Cuenta seleccionada: (ninguna)")
            self.clear_items_view()
            return

        try:
            det = self.service.account_detail(self.selected_slot)
        except Exception:
            self.lbl_selected.config(text="Cuenta seleccionada: (ninguna)")
            self.clear_items_view()
            return

        self.lbl_selected.config(text=f"Cuenta: [{det['slot']}] {det['nombre']}")

        for i in self.tv_items.get_children():
            self.tv_items.delete(i)

        for line in det["lines"]:
            self.tv_items.insert(
                "",
                "end",
                values=(
                    line["product_id"],
                    line["nombre"],
                    line["qty"],
                    money_from_cents(line["unit_price_centavos"]),
                    money_from_cents(line["line_subtotal_centavos"]),
                ),
            )

        self.lbl_sub.config(text=f"Subtotal: {money_from_cents(det['subtotal_centavos'])}")
        self.lbl_iva.config(text=f"IVA 13%: {money_from_cents(det['iva_centavos'])}")
        self.lbl_tot.config(text=f"Total: {money_from_cents(det['total_centavos'])}")

    # ---------------- Selección slot ----------------
    def select_slot(self, slot: int):
        # Si está libre, solo selecciona (no abre). Abrir se hace con botón "Abrir Mesa"
        self.selected_slot = slot if self.service.cuentas.get(slot) is not None else slot
        # Si está libre, no hay detalle. Si está abierta, muestra detalle.
        if self.service.cuentas.get(slot) is None:
            self.lbl_selected.config(text=f"Mesa {slot} (LIBRE) - toca 'Abrir Mesa'")
            self.clear_items_view()
        else:
            self.refresh_account_detail()
        self.refresh_accounts_tiles()

    # ---------------- Cuentas (touch) ----------------
    def gui_open_account_touch(self):
        # Si ya hay mesa seleccionada, usa ese slot. Si no, pregunta.
        slot = self.selected_slot
        if slot is None or slot < 1 or slot > MAX_CUENTAS:
            slot = simpledialog.askinteger("Abrir cuenta", "Slot (1..10):", minvalue=1, maxvalue=MAX_CUENTAS, parent=self)
            if slot is None:
                return

        if self.service.cuentas.get(slot) is not None:
            messagebox.showerror("Abrir", "Esa mesa ya está abierta.", parent=self)
            return

        name = simpledialog.askstring("Abrir cuenta", "Nombre (ej. Mesa 3, Terraza, Carlos):", parent=self)
        if name is None:
            name = ""

        try:
            self.service.open_account(slot, name)
            self.selected_slot = slot
            self.refresh_accounts_tiles()
            self.refresh_account_detail()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def gui_add_item(self):
        if self.selected_slot is None:
            messagebox.showinfo("Agregar", "Selecciona una mesa primero.", parent=self)
            return
        if self.service.cuentas.get(self.selected_slot) is None:
            messagebox.showinfo("Agregar", "Esa mesa está libre. Abre la mesa primero.", parent=self)
            return

        text = self.cb_products.get()
        if not text or text not in self.product_map:
            messagebox.showerror("Agregar", "Selecciona un producto válido.", parent=self)
            return

        try:
            qty = int(self.qty_var.get())
        except Exception:
            messagebox.showerror("Agregar", "Cantidad inválida.", parent=self)
            return

        pid = self.product_map[text]
        try:
            self.service.add_item(self.selected_slot, pid, qty)
            self.refresh_inventory()
            self.refresh_products_combobox()
            self.refresh_account_detail()
            self.refresh_accounts_tiles()
            self.refresh_catalog()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def gui_remove_item(self):
        if self.selected_slot is None:
            messagebox.showinfo("Quitar", "Selecciona una mesa primero.", parent=self)
            return
        if self.service.cuentas.get(self.selected_slot) is None:
            messagebox.showinfo("Quitar", "Esa mesa está libre.", parent=self)
            return

        sel = self.tv_items.selection()
        if not sel:
            messagebox.showinfo("Quitar", "Selecciona un producto en la lista.", parent=self)
            return

        values = self.tv_items.item(sel[0], "values")
        pid = int(values[0])

        try:
            qty = int(self.qty_var.get())
        except Exception:
            messagebox.showerror("Quitar", "Cantidad inválida.", parent=self)
            return

        try:
            self.service.remove_item(self.selected_slot, pid, qty)
            self.refresh_inventory()
            self.refresh_products_combobox()
            self.refresh_account_detail()
            self.refresh_accounts_tiles()
            self.refresh_catalog()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def gui_close_account(self):
        if self.selected_slot is None:
            messagebox.showinfo("Cobrar", "Selecciona una mesa primero.", parent=self)
            return

        cuenta = self.service.cuentas.get(self.selected_slot)
        if cuenta is None:
            messagebox.showinfo("Cobrar", "Esa mesa está libre.", parent=self)
            return

        # Validar que haya caja abierta
        try:
            session = self.service.get_active_cash_session()
            if not session:
                if messagebox.askyesno(
                    "Caja cerrada",
                    "No hay caja abierta.\n\n¿Deseas abrir la caja ahora?",
                    parent=self
                ):
                    self.gui_cash_open()
                    # Verificar nuevamente
                    session = self.service.get_active_cash_session()
                    if not session:
                        return  # Usuario canceló la apertura
                else:
                    return
        except Exception as e:
            messagebox.showerror("Error", f"Error al verificar caja: {e}", parent=self)
            return

        if not messagebox.askyesno("Confirmar", f"¿Cobrar y cerrar '{cuenta.nombre}'?\n\nSe generará recibo PDF y TXT.", parent=self):
            return

        try:
            res = self.service.close_account(self.selected_slot)
            if res.get("recorded"):
                total_centavos = res["total_centavos"]
                closed_account_id = res.get("closed_account_id")
                receipt_no = res.get("receipt_no")

                # Capturar método de pago
                payment_dlg = PaymentMethodDialog(self, total_centavos)
                self.wait_window(payment_dlg)
                
                if payment_dlg.result is None:
                    messagebox.showwarning("Cancelado", "No se registró el método de pago.", parent=self)
                    self.selected_slot = None
                    self.refresh_all()
                    return

                payment_data = payment_dlg.result
                
                # Registrar pago en BD
                try:
                    from pos_core import rewrite_receipt_with_payment
                    self.service.record_payment(
                        closed_account_id,
                        receipt_no,
                        payment_data["method"],
                        total_centavos,
                        payment_data.get("cash_received"),
                        payment_data.get("change"),
                        self.current_user
                    )
                    
                    # Regenerar recibos con info de pago
                    rewrite_receipt_with_payment(
                        self.service.db,
                        closed_account_id,
                        receipt_no,
                        payment_data["method"],
                        payment_data.get("cash_received"),
                        payment_data.get("change")
                    )
                    
                    # Actualizar rutas de recibos para impresión
                    from datetime import date
                    bd = date.today().isoformat()
                    recdir = f"receipts/{bd}"
                    receipt_txt = f"{recdir}/recibo_{bd}_{receipt_no}.txt"
                    receipt_pdf = f"{recdir}/recibo_{bd}_{receipt_no}.pdf"
                    
                except Exception as e:
                    messagebox.showerror("Error", f"Error al registrar pago: {e}", parent=self)

                # Mensaje de éxito
                msg_parts = [
                    f"Subtotal: {money_from_cents(res['subtotal_centavos'])}",
                    f"IVA 13%: {money_from_cents(res['iva_centavos'])}",
                    f"TOTAL: {money_from_cents(total_centavos)}",
                    "",
                    f"Método: {payment_data['method']}"
                ]
                
                if payment_data["method"] == "EFECTIVO":
                    msg_parts.append(f"Recibido: {money_from_cents(payment_data['cash_received'])}")
                    msg_parts.append(f"Vuelto: {money_from_cents(payment_data['change'])}")
                
                msg_parts.append(f"\nRecibo #: {receipt_no}")
                
                messagebox.showinfo("Cuenta cerrada", "\n".join(msg_parts), parent=self)

                # Preguntar imprimir al instante (TXT recomendado para térmica)
                if messagebox.askyesno("Imprimir", "¿Imprimir TICKET (TXT) ahora en impresora predeterminada?", parent=self):
                    try:
                        print_path_in_os(receipt_txt)
                    except Exception as e:
                        messagebox.showerror("Imprimir", str(e), parent=self)

            else:
                messagebox.showinfo("Cuenta cerrada", "Cuenta vacía: se liberó sin registrar venta.", parent=self)

            self.selected_slot = None
            self.refresh_all()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def gui_free_empty_selected(self):
        if self.selected_slot is None:
            messagebox.showinfo("Liberar", "Selecciona una mesa primero.", parent=self)
            return
        c = self.service.cuentas.get(self.selected_slot)
        if c is None:
            messagebox.showinfo("Liberar", "Esa mesa ya está libre.", parent=self)
            return
        if not c.is_empty():
            messagebox.showerror("Liberar", "Solo se puede liberar si la cuenta está vacía.", parent=self)
            return
        if not messagebox.askyesno("Confirmar", f"¿Liberar cuenta vacía '{c.nombre}'?", parent=self):
            return
        try:
            self.service.free_empty_account(self.selected_slot)
            self.selected_slot = None
            self.refresh_all()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    # ---------------- Inventario ----------------
    def _selected_product_id_from_inventory(self):
        sel = self.tv_inv.selection()
        if not sel:
            return None
        values = self.tv_inv.item(sel[0], "values")
        return int(values[0])

    def gui_new_product(self):
        dlg = ProductEditor(self, "Nuevo producto", initial={"nombre": "", "tipo": "bebida", "precio": 0.0, "stock": 0})
        self.wait_window(dlg)
        if dlg.result is None:
            return
        try:
            self.service.create_product(dlg.result["nombre"], dlg.result["tipo"], dlg.result["precio"], dlg.result["stock"])
            self.refresh_inventory()
            self.refresh_products_combobox()
            self.refresh_catalog()
            messagebox.showinfo("OK", "Producto creado.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def gui_edit_product(self):
        pid = self._selected_product_id_from_inventory()
        if pid is None:
            messagebox.showinfo("Editar", "Selecciona un producto.", parent=self)
            return
        prod = self.service.get_product(pid)
        if not prod:
            messagebox.showerror("Editar", "Producto no existe.", parent=self)
            return
        initial = {"nombre": prod.nombre, "tipo": prod.tipo, "precio": prod.precio_centavos / 100, "stock": prod.stock}
        dlg = ProductEditor(self, f"Editar producto (ID {pid})", initial=initial)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        try:
            self.service.update_product(pid, dlg.result["nombre"], dlg.result["tipo"], dlg.result["precio"], dlg.result["stock"])
            self.refresh_inventory()
            self.refresh_products_combobox()
            self.refresh_catalog()
            messagebox.showinfo("OK", "Producto actualizado.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def gui_adjust_stock(self):
        pid = self._selected_product_id_from_inventory()
        if pid is None:
            messagebox.showinfo("Stock", "Selecciona un producto.", parent=self)
            return
        prod = self.service.get_product(pid)
        if not prod:
            messagebox.showerror("Stock", "Producto no existe.", parent=self)
            return

        mode = messagebox.askyesno(
            "Ajustar stock",
            "¿Quieres SUMAR stock?\n\nSí = Sumar\nNo = Reemplazar (stock exacto)",
            parent=self
        )

        if mode:
            delta = simpledialog.askinteger("Sumar stock", f"¿Cuántas unidades agregar a '{prod.nombre}'?",
                                            minvalue=1, maxvalue=999999, parent=self)
            if delta is None:
                return
            try:
                self.service.adjust_stock(pid, delta)
                self.refresh_inventory()
                self.refresh_products_combobox()
                self.refresh_catalog()
                messagebox.showinfo("OK", f"Nuevo stock: {self.service.get_product(pid).stock}", parent=self)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)
        else:
            new_stock = simpledialog.askinteger("Reemplazar stock", f"Nuevo stock EXACTO para '{prod.nombre}':",
                                                minvalue=0, maxvalue=999999, parent=self)
            if new_stock is None:
                return
            try:
                self.service.set_stock(pid, new_stock)
                self.refresh_inventory()
                self.refresh_products_combobox()
                self.refresh_catalog()
                messagebox.showinfo("OK", f"Nuevo stock: {self.service.get_product(pid).stock}", parent=self)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

    # ---------------- Usuarios ----------------
    def gui_users(self):
        if not self.is_admin():
            messagebox.showerror("Permisos", "Solo ADMIN puede gestionar usuarios.", parent=self)
            return
        UsersManager(self, self.service)

    # ---------------- Reportes / Recibos ----------------
    def load_report(self):
        bd = self.ent_report_date.get().strip()
        if not bd:
            return
        try:
            rep = self.service.daily_report(bd)
        except Exception as e:
            messagebox.showerror("Reporte", str(e), parent=self)
            return

        self.lbl_rep_cnt.config(text=f"Cuentas cerradas: {rep['cuentas_cerradas']}")
        self.lbl_rep_sub.config(text=f"Subtotal: {money_from_cents(rep['subtotal_centavos'])}")
        self.lbl_rep_iva.config(text=f"IVA: {money_from_cents(rep['iva_centavos'])}")
        self.lbl_rep_tot.config(text=f"Total: {money_from_cents(rep['total_centavos'])}")

        for i in self.tv_sales.get_children():
            self.tv_sales.delete(i)
        for r in rep["ventas_por_producto"]:
            self.tv_sales.insert("", "end", values=(r["product_nombre"], r["product_tipo"], int(r["qty_total"]), money_from_cents(int(r["total_total"]))))

        for i in self.tv_receipts.get_children():
            self.tv_receipts.delete(i)
        for rc in self.service.list_receipts(bd):
            ts = rc["ts"].split(" ")[1]
            self.tv_receipts.insert("", "end", iid=str(rc["id"]), values=(rc["receipt_no"], rc["cuenta_label"], ts, os.path.basename(rc["pdf_path"])))

    def gui_export_csv_quick_today(self):
        # Export rápido HOY
        bd = self.service.business_date()
        directory = filedialog.askdirectory(title="Selecciona carpeta para exportar CSV")
        if not directory:
            return
        try:
            paths = self.service.export_csv(bd, directory)
            messagebox.showinfo("Exportación lista", "CSV generados:\n\n" + "\n".join(os.path.basename(p) for p in paths.values()), parent=self)
        except Exception as e:
            messagebox.showerror("Exportar", str(e), parent=self)

    def gui_export_csv(self):
        bd = self.ent_report_date.get().strip()
        if not bd:
            messagebox.showerror("Exportar", "Indica una fecha válida (YYYY-MM-DD).", parent=self)
            return
        directory = filedialog.askdirectory(title="Selecciona carpeta para exportar CSV")
        if not directory:
            return
        try:
            paths = self.service.export_csv(bd, directory)
            messagebox.showinfo("Exportación lista", "CSV generados:\n\n" + "\n".join(os.path.basename(p) for p in paths.values()), parent=self)
        except Exception as e:
            messagebox.showerror("Exportar", str(e), parent=self)

    def _selected_receipt_id(self):
        sel = self.tv_receipts.selection()
        if not sel:
            return None
        return int(sel[0])

    def gui_open_receipt_pdf(self):
        rid = self._selected_receipt_id()
        if rid is None:
            messagebox.showinfo("Recibos", "Selecciona un recibo.", parent=self)
            return
        row = self.db.get_receipt(rid)
        if not row:
            messagebox.showerror("Recibos", "Recibo no existe.", parent=self)
            return
        open_path_in_os(row["pdf_path"])

    def gui_open_receipt_txt(self):
        rid = self._selected_receipt_id()
        if rid is None:
            messagebox.showinfo("Recibos", "Selecciona un recibo.", parent=self)
            return
        row = self.db.get_receipt(rid)
        if not row:
            messagebox.showerror("Recibos", "Recibo no existe.", parent=self)
            return
        open_path_in_os(row["txt_path"])

    def gui_print_receipt_pdf(self):
        rid = self._selected_receipt_id()
        if rid is None:
            messagebox.showinfo("Recibos", "Selecciona un recibo.", parent=self)
            return
        row = self.db.get_receipt(rid)
        if not row:
            messagebox.showerror("Recibos", "Recibo no existe.", parent=self)
            return
        try:
            print_path_in_os(row["pdf_path"])
            messagebox.showinfo("Imprimir", "Enviado a la impresora predeterminada.", parent=self)
        except Exception as e:
            messagebox.showerror("Imprimir", str(e), parent=self)

    def gui_print_receipt_txt(self):
        rid = self._selected_receipt_id()
        if rid is None:
            messagebox.showinfo("Recibos", "Selecciona un recibo.", parent=self)
            return
        row = self.db.get_receipt(rid)
        if not row:
            messagebox.showerror("Recibos", "Recibo no existe.", parent=self)
            return
        try:
            print_path_in_os(row["txt_path"])
            messagebox.showinfo("Imprimir", "Enviado a la impresora predeterminada.", parent=self)
        except Exception as e:
            messagebox.showerror("Imprimir", str(e), parent=self)

    def gui_open_receipts_folder(self):
        bd = self.ent_report_date.get().strip()
        folder = os.path.join(app_base_dir(), "receipts", bd)
        os.makedirs(folder, exist_ok=True)
        open_path_in_os(folder)

    # ---------------- Control de Caja ----------------
    def update_cash_status(self):
        """Actualiza el label de estado de caja y visibilidad de botones."""
        try:
            session = self.service.get_active_cash_session()
            if session:
                opening = session["opening_amount_centavos"] / 100
                user = session["opened_by"]
                self.lbl_cash_status.config(
                    text=f"🔓 CAJA ABIERTA | Apertura: ₡{opening:,.2f} | Usuario: {user}",
                    fg=PALETTE["success"]
                )
                self.btn_cash_open.config(state="disabled")
                self.btn_cash_close.config(state="normal")
            else:
                self.lbl_cash_status.config(
                    text="🔒 CAJA CERRADA | Debes abrir caja para cobrar",
                    fg=PALETTE["danger"]
                )
                self.btn_cash_open.config(state="normal")
                self.btn_cash_close.config(state="disabled")
        except Exception as e:
            self.lbl_cash_status.config(text=f"Error: {e}", fg=PALETTE["danger"])

    def gui_cash_open(self):
        """Apertura de caja."""
        try:
            existing = self.service.get_active_cash_session()
            if existing:
                messagebox.showwarning("Caja", "Ya hay una caja abierta para hoy.", parent=self)
                return

            dlg = CashOpenDialog(self)
            self.wait_window(dlg)
            
            if dlg.result is None:
                return

            opening_amount = dlg.result
            self.service.open_cash_session(opening_amount, self.current_user)
            
            messagebox.showinfo(
                "Caja abierta",
                f"Caja abierta con ₡{opening_amount:,.2f}\nUsuario: {self.current_user}",
                parent=self
            )
            
            self.update_cash_status()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def gui_cash_close(self):
        """Cierre de caja (solo ADMIN)."""
        if not self.is_admin():
            messagebox.showerror("Permisos", "Solo ADMIN puede cerrar la caja.", parent=self)
            return

        try:
            session = self.service.get_active_cash_session()
            if not session:
                messagebox.showwarning("Caja", "No hay caja abierta para cerrar.", parent=self)
                return

            # Calcular efectivo esperado
            session_id = int(session["id"])
            bd = self.service.business_date()
            expected_centavos = self.service.calculate_expected_cash(session_id, bd)
            expected_colones = expected_centavos / 100

            dlg = CashCloseDialog(self, expected_colones)
            self.wait_window(dlg)
            
            if dlg.result is None:
                return

            counted = dlg.result["counted"]
            notes = dlg.result["notes"]
            
            result = self.service.close_cash_session(counted, self.current_user, notes)
            
            diff = result["diff_cash_centavos"] / 100
            diff_color = "verde" if diff >= 0 else "rojo"
            diff_sign = "+" if diff >= 0 else ""
            
            msg = (
                f"Caja cerrada por: {self.current_user}\n\n"
                f"Efectivo esperado: ₡{expected_colones:,.2f}\n"
                f"Efectivo contado: ₡{counted:,.2f}\n"
                f"Diferencia: {diff_sign}₡{diff:,.2f} ({diff_color})\n"
            )
            
            if notes:
                msg += f"\nNotas: {notes}"
            
            messagebox.showinfo("Cierre de caja", msg, parent=self)
            self.update_cash_status()
            
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def gui_cash_report(self):
        """Muestra reporte de caja."""
        try:
            session = self.service.get_active_cash_session()
            if not session:
                messagebox.showinfo("Reporte", "No hay caja abierta para reportar.", parent=self)
                return

            report = self.service.cash_report()
            
            opening = report["opening_amount_centavos"] / 100
            efectivo_total = report["efectivo_total_centavos"] / 100
            tarjeta_total = report["tarjeta_total_centavos"] / 100
            sinpe_total = report["sinpe_total_centavos"] / 100
            expected = report["expected_cash_centavos"] / 100
            
            msg = (
                f"═══ REPORTE DE CAJA ═══\n\n"
                f"Apertura: ₡{opening:,.2f}\n\n"
                f"VENTAS:\n"
                f"  💵 Efectivo: ₡{efectivo_total:,.2f} ({report['efectivo_count']} ventas)\n"
                f"  💳 Tarjeta: ₡{tarjeta_total:,.2f} ({report['tarjeta_count']} ventas)\n"
                f"  📱 SINPE: ₡{sinpe_total:,.2f} ({report['sinpe_count']} ventas)\n\n"
                f"EFECTIVO ESPERADO: ₡{expected:,.2f}\n"
                f"(Apertura + Efectivo)"
            )
            
            messagebox.showinfo("Reporte de Caja", msg, parent=self)
            
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def gui_close_day(self):
        if not self.is_admin():
            messagebox.showerror("Permisos", "Solo ADMIN puede hacer cierre diario.", parent=self)
            return

        bd = self.service.business_date()
        abiertas = self.service.can_close_day()
        if abiertas:
            msg = "No puedes cerrar el día: hay cuentas con consumo abierto:\n\n" + "\n".join(f"Slot {s}: {n}" for s, n in abiertas)
            messagebox.showerror("Cierre diario", msg, parent=self)
            return

        if not messagebox.askyesno(
            "Confirmar cierre",
            f"¿Hacer cierre diario de HOY ({bd})?\n\nEsto:\n- registra el cierre de hoy\n- libera todas las mesas",
            parent=self
        ):
            return

        try:
            res = self.service.close_day()
            messagebox.showinfo(
                "Cierre registrado",
                f"Día: {res['business_date']}\n"
                f"Cuentas cerradas: {res['cuentas_cerradas']}\n"
                f"Total: {money_from_cents(res['total_centavos'])}\n\n"
                f"✅ Mesas liberadas.",
                parent=self
            )
            self.selected_slot = None
            self.refresh_all()
        except Exception as e:
            messagebox.showerror("Cierre diario", str(e), parent=self)

    # ---------------- Close ----------------
    def on_close(self):
        try:
            self.db.close()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = POSApp()
    app.mainloop()
