# pos_core.py
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import sys
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, Optional, List, Tuple, Any

# PDF receipts
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


IVA_RATE = 0.13
MAX_CUENTAS = 10
LOW_STOCK_THRESHOLD = 3

# Ajusta si quieres branding
BAR_NAME = "Mi Bar"
BAR_SUBTITLE = "POS - Recibo"


def app_base_dir() -> str:
    """
    Base para archivos (DB, recibos, exports).
    - Si está "congelado" (exe), usa la carpeta del exe.
    - Si no, usa la carpeta del script.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def money_from_cents(cents: int) -> str:
    return f"₡{cents / 100:,.2f}"


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def system_business_date() -> str:
    """Siempre retorna la fecha REAL del sistema."""
    return date.today().isoformat()


def safe_filename(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\-_]+", "_", s)
    return s.strip("_") or "cuenta"


# ------------------ Seguridad simple (password hashing) ------------------

def _pbkdf2_hash(password: str, salt_hex: str, iterations: int = 200_000) -> str:
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return dk.hex()


def make_password_hash(password: str) -> Tuple[str, str, int]:
    salt_hex = secrets.token_hex(16)
    iterations = 200_000
    hash_hex = _pbkdf2_hash(password, salt_hex, iterations)
    return salt_hex, hash_hex, iterations


def verify_password(password: str, salt_hex: str, hash_hex: str, iterations: int) -> bool:
    test = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()
    # comparación constante
    return secrets.compare_digest(test, hash_hex)


@dataclass(frozen=True)
class Producto:
    id: int
    nombre: str
    tipo: str  # "bebida" o "comida"
    precio_centavos: int
    stock: int


class Cuenta:
    def __init__(self, slot_id: int, nombre: str, opened_date: str):
        self.slot_id = slot_id
        self.nombre = nombre
        self.opened_date = opened_date
        self.items: Dict[int, int] = {}  # product_id -> qty

    def add_item(self, product_id: int, qty: int) -> None:
        self.items[product_id] = self.items.get(product_id, 0) + qty
        if self.items[product_id] <= 0:
            self.items.pop(product_id, None)

    def remove_item(self, product_id: int, qty: int) -> bool:
        if product_id not in self.items:
            return False
        if qty <= 0 or qty > self.items[product_id]:
            return False
        self.items[product_id] -= qty
        if self.items[product_id] == 0:
            del self.items[product_id]
        return True

    def is_empty(self) -> bool:
        return len(self.items) == 0


class InventarioDB:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(app_base_dir(), "pos_bar.sqlite")

        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

        self._init_schema()
        self._seed_if_empty()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()

        # Productos
        cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL,
            precio_centavos INTEGER NOT NULL,
            stock INTEGER NOT NULL
        );
        """)

        # Usuarios (roles)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            role TEXT NOT NULL CHECK (role IN ('admin','cajero')),
            salt_hex TEXT NOT NULL,
            hash_hex TEXT NOT NULL,
            iterations INTEGER NOT NULL,
            created_ts TEXT NOT NULL
        );
        """)

        # Cuentas abiertas (persistencia)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS open_accounts (
            slot INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            opened_date TEXT NOT NULL,
            opened_ts TEXT NOT NULL
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS open_account_items (
            slot INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            PRIMARY KEY (slot, product_id),
            FOREIGN KEY (slot) REFERENCES open_accounts(slot) ON DELETE CASCADE
        );
        """)

        # Ventas / líneas
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            business_date TEXT NOT NULL,
            cuenta_label TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            product_nombre TEXT NOT NULL,
            product_tipo TEXT NOT NULL,
            qty INTEGER NOT NULL,
            unit_price_centavos INTEGER NOT NULL,
            line_subtotal_centavos INTEGER NOT NULL,
            line_iva_centavos INTEGER NOT NULL,
            line_total_centavos INTEGER NOT NULL
        );
        """)

        # Cuentas cerradas
        cur.execute("""
        CREATE TABLE IF NOT EXISTS closed_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            business_date TEXT NOT NULL,
            cuenta_label TEXT NOT NULL,
            subtotal_centavos INTEGER NOT NULL,
            iva_centavos INTEGER NOT NULL,
            total_centavos INTEGER NOT NULL,
            items_json TEXT NOT NULL
        );
        """)

        # Cierres diarios
        cur.execute("""
        CREATE TABLE IF NOT EXISTS closures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            business_date TEXT NOT NULL,
            total_subtotal_centavos INTEGER NOT NULL,
            total_iva_centavos INTEGER NOT NULL,
            total_centavos INTEGER NOT NULL,
            cuentas_cerradas INTEGER NOT NULL
        );
        """)

        # Recibos (para reimpresión)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            business_date TEXT NOT NULL,
            receipt_no INTEGER NOT NULL,
            cuenta_label TEXT NOT NULL,
            closed_account_id INTEGER NOT NULL,
            pdf_path TEXT NOT NULL,
            txt_path TEXT NOT NULL,
            FOREIGN KEY (closed_account_id) REFERENCES closed_accounts(id) ON DELETE CASCADE
        );
        """)

        # Sesiones de caja
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cash_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_date TEXT NOT NULL,
            opened_ts TEXT NOT NULL,
            opened_by TEXT NOT NULL,
            opening_amount_centavos INTEGER NOT NULL,
            closed_ts TEXT,
            closed_by TEXT,
            counted_cash_centavos INTEGER,
            expected_cash_centavos INTEGER,
            diff_cash_centavos INTEGER,
            notes TEXT
        );
        """)

        # Pagos (métodos de pago por cuenta cerrada)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_date TEXT NOT NULL,
            closed_account_id INTEGER NOT NULL,
            receipt_no INTEGER NOT NULL,
            method TEXT NOT NULL CHECK (method IN ('EFECTIVO','TARJETA','SINPE')),
            total_centavos INTEGER NOT NULL,
            cash_received_centavos INTEGER,
            change_centavos INTEGER,
            created_ts TEXT NOT NULL,
            created_by TEXT NOT NULL,
            FOREIGN KEY (closed_account_id) REFERENCES closed_accounts(id) ON DELETE CASCADE
        );
        """)

        self.conn.commit()

    def _seed_if_empty(self) -> None:
        cur = self.conn.cursor()

        # Seed productos si están vacíos
        cur.execute("SELECT COUNT(*) AS c FROM products;")
        if int(cur.fetchone()["c"]) == 0:
            seed = [
                ("Cerveza Pilsen", "bebida", 1600_00, 48),
                ("Cerveza Imperial", "bebida", 1600_00, 48),
                ("Gaseosa", "bebida", 1200_00, 24),
                ("Agua", "bebida", 1000_00, 24),
                ("Hamburguesa", "comida", 3500_00, 15),
                ("Papas fritas", "comida", 2000_00, 20),
            ]
            cur.executemany(
                "INSERT INTO products(nombre, tipo, precio_centavos, stock) VALUES(?,?,?,?);",
                seed
            )

        # Seed usuarios si están vacíos
        cur.execute("SELECT COUNT(*) AS c FROM users;")
        if int(cur.fetchone()["c"]) == 0:
            # ⚠️ Cambia contraseñas luego desde la GUI (Usuarios)
            self.create_user("admin", "admin123", "admin")
            self.create_user("cajero", "cajero123", "cajero")

        self.conn.commit()

    # ---------------- Usuarios ----------------

    def create_user(self, username: str, password: str, role: str) -> None:
        username = username.strip().lower()
        role = role.strip().lower()

        if not username:
            raise ValueError("Usuario inválido.")
        if role not in ("admin", "cajero"):
            raise ValueError("Rol inválido (admin/cajero).")
        if len(password) < 4:
            raise ValueError("Contraseña muy corta (mín 4).")

        salt_hex, hash_hex, iters = make_password_hash(password)

        cur = self.conn.cursor()
        try:
            cur.execute("""
            INSERT INTO users(username, role, salt_hex, hash_hex, iterations, created_ts)
            VALUES(?,?,?,?,?,?);
            """, (username, role, salt_hex, hash_hex, iters, now_ts()))
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError("Ya existe ese usuario.")

    def list_users(self) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT username, role, created_ts FROM users ORDER BY role, username;")
        return cur.fetchall()

    def delete_user(self, username: str) -> None:
        username = username.strip().lower()
        if username in ("admin",):
            raise ValueError("No se puede borrar el usuario admin base.")
        cur = self.conn.cursor()
        cur.execute("DELETE FROM users WHERE username=?;", (username,))
        if cur.rowcount == 0:
            raise ValueError("Usuario no existe.")
        self.conn.commit()

    def set_password(self, username: str, new_password: str) -> None:
        username = username.strip().lower()
        if len(new_password) < 4:
            raise ValueError("Contraseña muy corta (mín 4).")
        salt_hex, hash_hex, iters = make_password_hash(new_password)
        cur = self.conn.cursor()
        cur.execute("""
        UPDATE users
           SET salt_hex=?, hash_hex=?, iterations=?
         WHERE username=?;
        """, (salt_hex, hash_hex, iters, username))
        if cur.rowcount == 0:
            raise ValueError("Usuario no existe.")
        self.conn.commit()

    def authenticate_user(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        username = username.strip().lower()
        cur = self.conn.cursor()
        cur.execute("SELECT username, role, salt_hex, hash_hex, iterations FROM users WHERE username=?;", (username,))
        r = cur.fetchone()
        if not r:
            return False, None
        ok = verify_password(password, r["salt_hex"], r["hash_hex"], int(r["iterations"]))
        return ok, (r["role"] if ok else None)

    # ---------------- Productos (CRUD) ----------------

    def create_product(self, nombre: str, tipo: str, precio_centavos: int, stock: int) -> int:
        nombre = nombre.strip()
        tipo = tipo.strip().lower()

        if not nombre:
            raise ValueError("Nombre no puede estar vacío.")
        if tipo not in ("bebida", "comida"):
            raise ValueError("Tipo inválido. Debe ser 'bebida' o 'comida'.")
        if precio_centavos < 0:
            raise ValueError("Precio inválido.")
        if stock < 0:
            raise ValueError("Stock inválido.")

        cur = self.conn.cursor()
        try:
            cur.execute(
                "INSERT INTO products(nombre, tipo, precio_centavos, stock) VALUES(?,?,?,?);",
                (nombre, tipo, precio_centavos, stock)
            )
            self.conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            raise ValueError("Ya existe un producto con ese nombre.")

    def update_product(self, product_id: int, nombre: str, tipo: str, precio_centavos: int, stock: int) -> None:
        nombre = nombre.strip()
        tipo = tipo.strip().lower()

        if not nombre:
            raise ValueError("Nombre no puede estar vacío.")
        if tipo not in ("bebida", "comida"):
            raise ValueError("Tipo inválido. Debe ser 'bebida' o 'comida'.")
        if precio_centavos < 0:
            raise ValueError("Precio inválido.")
        if stock < 0:
            raise ValueError("Stock inválido.")

        cur = self.conn.cursor()
        try:
            cur.execute("""
            UPDATE products
               SET nombre=?, tipo=?, precio_centavos=?, stock=?
             WHERE id=?;
            """, (nombre, tipo, precio_centavos, stock, product_id))
            if cur.rowcount == 0:
                raise ValueError("Producto no existe.")
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError("No se pudo actualizar: nombre duplicado.")

    def set_stock(self, product_id: int, new_stock: int) -> None:
        if new_stock < 0:
            raise ValueError("Stock inválido.")
        cur = self.conn.cursor()
        cur.execute("UPDATE products SET stock=? WHERE id=?;", (new_stock, product_id))
        if cur.rowcount == 0:
            raise ValueError("Producto no existe.")
        self.conn.commit()

    # ---------------- Inventario / consultas ----------------

    def list_products(self) -> List[Producto]:
        cur = self.conn.cursor()
        cur.execute("SELECT id, nombre, tipo, precio_centavos, stock FROM products ORDER BY tipo, nombre;")
        rows = cur.fetchall()
        return [Producto(int(r["id"]), r["nombre"], r["tipo"], int(r["precio_centavos"]), int(r["stock"])) for r in rows]

    def get_product(self, product_id: int) -> Optional[Producto]:
        cur = self.conn.cursor()
        cur.execute("SELECT id, nombre, tipo, precio_centavos, stock FROM products WHERE id=?;", (product_id,))
        r = cur.fetchone()
        if not r:
            return None
        return Producto(int(r["id"]), r["nombre"], r["tipo"], int(r["precio_centavos"]), int(r["stock"]))

    def adjust_stock(self, product_id: int, delta: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT stock FROM products WHERE id=?;", (product_id,))
        row = cur.fetchone()
        if not row:
            return False

        current = int(row["stock"])
        new_stock = current + delta
        if new_stock < 0:
            return False

        cur.execute("UPDATE products SET stock=? WHERE id=?;", (new_stock, product_id))
        self.conn.commit()
        return True

    # ---------------- Persistencia cuentas abiertas ----------------

    def upsert_open_account(self, slot: int, nombre: str, opened_date: str) -> None:
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO open_accounts(slot, nombre, opened_date, opened_ts)
        VALUES(?,?,?,?)
        ON CONFLICT(slot) DO UPDATE SET
            nombre=excluded.nombre,
            opened_date=excluded.opened_date,
            opened_ts=excluded.opened_ts;
        """, (slot, nombre, opened_date, now_ts()))
        self.conn.commit()

    def delete_open_account(self, slot: int) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM open_accounts WHERE slot=?;", (slot,))
        self.conn.commit()

    def clear_all_open_accounts(self) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM open_accounts;")  # cascada borra items
        self.conn.commit()

    def list_open_accounts(self) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT slot, nombre, opened_date, opened_ts FROM open_accounts ORDER BY slot;")
        return cur.fetchall()

    def list_open_items(self, slot: int) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("""
        SELECT product_id, qty
        FROM open_account_items
        WHERE slot=?
        ORDER BY product_id;
        """, (slot,))
        return cur.fetchall()

    def upsert_open_item(self, slot: int, product_id: int, qty: int) -> None:
        cur = self.conn.cursor()
        if qty <= 0:
            cur.execute("DELETE FROM open_account_items WHERE slot=? AND product_id=?;", (slot, product_id))
        else:
            cur.execute("""
            INSERT INTO open_account_items(slot, product_id, qty)
            VALUES(?,?,?)
            ON CONFLICT(slot, product_id) DO UPDATE SET
                qty=excluded.qty;
            """, (slot, product_id, qty))
        self.conn.commit()

    # ---------------- Ventas / Cierres ----------------

    def record_closed_account(
        self,
        business_date: str,
        cuenta_label: str,
        subtotal_centavos: int,
        iva_centavos: int,
        total_centavos: int,
        items_json: str
    ) -> int:
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO closed_accounts(ts, business_date, cuenta_label, subtotal_centavos, iva_centavos, total_centavos, items_json)
        VALUES(?,?,?,?,?,?,?);
        """, (now_ts(), business_date, cuenta_label, subtotal_centavos, iva_centavos, total_centavos, items_json))
        self.conn.commit()
        return int(cur.lastrowid)

    def record_sales_line(
        self,
        business_date: str,
        cuenta_label: str,
        product: Producto,
        qty: int,
        line_subtotal_centavos: int,
        line_iva_centavos: int,
        line_total_centavos: int
    ) -> None:
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO sales_lines(
            ts, business_date, cuenta_label,
            product_id, product_nombre, product_tipo,
            qty, unit_price_centavos,
            line_subtotal_centavos, line_iva_centavos, line_total_centavos
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?);
        """, (
            now_ts(), business_date, cuenta_label,
            product.id, product.nombre, product.tipo,
            qty, product.precio_centavos,
            line_subtotal_centavos, line_iva_centavos, line_total_centavos
        ))
        self.conn.commit()

    def daily_summary(self, business_date: str) -> Tuple[int, int, int, int]:
        cur = self.conn.cursor()
        cur.execute("""
        SELECT
          COALESCE(SUM(subtotal_centavos),0) AS sub,
          COALESCE(SUM(iva_centavos),0) AS iva,
          COALESCE(SUM(total_centavos),0) AS tot,
          COUNT(*) AS cnt
        FROM closed_accounts
        WHERE business_date=?;
        """, (business_date,))
        r = cur.fetchone()
        return int(r["sub"]), int(r["iva"]), int(r["tot"]), int(r["cnt"])

    def daily_sales_by_product(self, business_date: str) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("""
        SELECT
          product_id,
          product_nombre,
          product_tipo,
          SUM(qty) AS qty_total,
          SUM(line_subtotal_centavos) AS subtotal_total,
          SUM(line_iva_centavos) AS iva_total,
          SUM(line_total_centavos) AS total_total
        FROM sales_lines
        WHERE business_date=?
        GROUP BY product_id, product_nombre, product_tipo
        ORDER BY product_tipo, product_nombre;
        """, (business_date,))
        return cur.fetchall()

    def list_closed_accounts(self, business_date: str) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("""
        SELECT id, ts, cuenta_label, subtotal_centavos, iva_centavos, total_centavos, items_json
        FROM closed_accounts
        WHERE business_date=?
        ORDER BY ts ASC;
        """, (business_date,))
        return cur.fetchall()

    def record_closure(self, business_date: str, sub: int, iva: int, tot: int, cnt: int) -> None:
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO closures(ts, business_date, total_subtotal_centavos, total_iva_centavos, total_centavos, cuentas_cerradas)
        VALUES(?,?,?,?,?,?);
        """, (now_ts(), business_date, sub, iva, tot, cnt))
        self.conn.commit()

    def closure_count_for_day(self, business_date: str) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM closures WHERE business_date=?;", (business_date,))
        return int(cur.fetchone()["c"])

    # ---------------- Recibos ----------------

    def next_receipt_no(self, business_date: str) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COALESCE(MAX(receipt_no), 0) AS m FROM receipts WHERE business_date=?;", (business_date,))
        return int(cur.fetchone()["m"]) + 1

    def insert_receipt(self, business_date: str, receipt_no: int, cuenta_label: str, closed_account_id: int, pdf_path: str, txt_path: str) -> int:
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO receipts(ts, business_date, receipt_no, cuenta_label, closed_account_id, pdf_path, txt_path)
        VALUES(?,?,?,?,?,?,?);
        """, (now_ts(), business_date, receipt_no, cuenta_label, closed_account_id, pdf_path, txt_path))
        self.conn.commit()
        return int(cur.lastrowid)

    def list_receipts(self, business_date: str) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("""
        SELECT id, ts, business_date, receipt_no, cuenta_label, pdf_path, txt_path
        FROM receipts
        WHERE business_date=?
        ORDER BY receipt_no ASC;
        """, (business_date,))
        return cur.fetchall()

    def get_receipt(self, receipt_id: int) -> Optional[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("""
        SELECT id, ts, business_date, receipt_no, cuenta_label, pdf_path, txt_path
        FROM receipts
        WHERE id=?;
        """, (receipt_id,))
        return cur.fetchone()

    # ------------------ Control de caja ------------------
    
    def get_active_cash_session(self, business_date: str) -> Optional[sqlite3.Row]:
        """Obtiene la sesión de caja activa (abierta) para la fecha."""
        cur = self.conn.cursor()
        cur.execute("""
        SELECT * FROM cash_sessions
        WHERE business_date=? AND closed_ts IS NULL
        ORDER BY id DESC LIMIT 1;
        """, (business_date,))
        return cur.fetchone()
    
    def open_cash_session(self, business_date: str, opening_amount_centavos: int, opened_by: str) -> int:
        """Abre una nueva sesión de caja."""
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO cash_sessions(business_date, opened_ts, opened_by, opening_amount_centavos)
        VALUES(?,?,?,?);
        """, (business_date, now_ts(), opened_by, opening_amount_centavos))
        self.conn.commit()
        return int(cur.lastrowid)
    
    def close_cash_session(self, session_id: int, counted_cash_centavos: int, 
                          expected_cash_centavos: int, closed_by: str, notes: str = "") -> None:
        """Cierra una sesión de caja."""
        diff = counted_cash_centavos - expected_cash_centavos
        cur = self.conn.cursor()
        cur.execute("""
        UPDATE cash_sessions
        SET closed_ts=?, closed_by=?, counted_cash_centavos=?, 
            expected_cash_centavos=?, diff_cash_centavos=?, notes=?
        WHERE id=?;
        """, (now_ts(), closed_by, counted_cash_centavos, expected_cash_centavos, diff, notes, session_id))
        self.conn.commit()
    
    def record_payment(self, business_date: str, closed_account_id: int, receipt_no: int,
                      method: str, total_centavos: int, cash_received_centavos: Optional[int],
                      change_centavos: Optional[int], created_by: str) -> int:
        """Registra un pago (método de pago)."""
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO payments(business_date, closed_account_id, receipt_no, method, 
                           total_centavos, cash_received_centavos, change_centavos, 
                           created_ts, created_by)
        VALUES(?,?,?,?,?,?,?,?,?);
        """, (business_date, closed_account_id, receipt_no, method, total_centavos,
              cash_received_centavos, change_centavos, now_ts(), created_by))
        self.conn.commit()
        return int(cur.lastrowid)
    
    def get_payments_for_session(self, business_date: str) -> List[sqlite3.Row]:
        """Obtiene todos los pagos de una fecha (sesión)."""
        cur = self.conn.cursor()
        cur.execute("""
        SELECT * FROM payments
        WHERE business_date=?
        ORDER BY created_ts ASC;
        """, (business_date,))
        return cur.fetchall()
    
    def get_payment_for_receipt(self, receipt_no: int, business_date: str) -> Optional[sqlite3.Row]:
        """Obtiene el pago de un recibo específico."""
        cur = self.conn.cursor()
        cur.execute("""
        SELECT * FROM payments
        WHERE receipt_no=? AND business_date=?
        LIMIT 1;
        """, (receipt_no, business_date))
        return cur.fetchone()

    def close(self) -> None:
        self.conn.close()


# ------------------ Generación de recibos ------------------

def write_receipt_txt(
    out_path: str,
    receipt_no: int,
    business_date: str,
    ts: str,
    cuenta_label: str,
    lines: List[dict],
    subtotal_centavos: int,
    iva_centavos: int,
    total_centavos: int
) -> None:
    # Ticket simple en texto, fácil para imprimir en impresoras térmicas
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"{BAR_NAME}\n")
        f.write(f"{BAR_SUBTITLE}\n")
        f.write("-" * 32 + "\n")
        f.write(f"Recibo #: {receipt_no}\n")
        f.write(f"Fecha: {business_date}  Hora: {ts.split(' ')[1]}\n")
        f.write(f"Cuenta: {cuenta_label}\n")
        f.write("-" * 32 + "\n")
        for it in lines:
            nombre = it["nombre"][:20]
            qty = it["qty"]
            unit = it["unit_price_centavos"]
            line_sub = it["line_subtotal_centavos"]
            f.write(f"{qty:>2} x {nombre:<20} {money_from_cents(line_sub):>9}\n")
        f.write("-" * 32 + "\n")
        f.write(f"Subtotal: {money_from_cents(subtotal_centavos)}\n")
        f.write(f"IVA 13%: {money_from_cents(iva_centavos)}\n")
        f.write(f"TOTAL:   {money_from_cents(total_centavos)}\n")
        f.write("-" * 32 + "\n")
        f.write("Gracias por su compra.\n")


def write_receipt_pdf(
    out_path: str,
    receipt_no: int,
    business_date: str,
    ts: str,
    cuenta_label: str,
    lines: List[dict],
    subtotal_centavos: int,
    iva_centavos: int,
    total_centavos: int
) -> None:
    # Ticket 80mm (aprox) en PDF
    width = 80 * mm  # 80mm
    # Altura dinámica
    base_h = 110 * mm
    line_h = 6 * mm
    height = base_h + len(lines) * line_h
    c = canvas.Canvas(out_path, pagesize=(width, height))

    x = 6 * mm
    y = height - 10 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, BAR_NAME)
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(x, y, BAR_SUBTITLE)
    y -= 6 * mm

    c.line(x, y, width - x, y)
    y -= 6 * mm

    c.setFont("Helvetica", 9)
    c.drawString(x, y, f"Recibo #: {receipt_no}")
    y -= 5 * mm
    c.drawString(x, y, f"Fecha: {business_date}")
    y -= 5 * mm
    c.drawString(x, y, f"Hora: {ts.split(' ')[1]}")
    y -= 5 * mm
    c.drawString(x, y, f"Cuenta: {cuenta_label}")
    y -= 6 * mm

    c.line(x, y, width - x, y)
    y -= 6 * mm

    # Encabezado
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x, y, "Cant  Producto")
    c.drawRightString(width - x, y, "Subtotal")
    y -= 5 * mm

    c.setFont("Helvetica", 8.5)
    for it in lines:
        qty = it["qty"]
        nombre = it["nombre"][:18]
        line_sub = it["line_subtotal_centavos"]

        c.drawString(x, y, f"{qty:>2}  {nombre}")
        c.drawRightString(width - x, y, money_from_cents(line_sub))
        y -= 5 * mm

    y -= 2 * mm
    c.line(x, y, width - x, y)
    y -= 6 * mm

    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Subtotal:")
    c.drawRightString(width - x, y, money_from_cents(subtotal_centavos))
    y -= 5 * mm
    c.drawString(x, y, "IVA 13%:")
    c.drawRightString(width - x, y, money_from_cents(iva_centavos))
    y -= 6 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "TOTAL:")
    c.drawRightString(width - x, y, money_from_cents(total_centavos))
    y -= 10 * mm

    c.setFont("Helvetica", 8.5)
    c.drawString(x, y, "Gracias por su compra.")

    c.showPage()
    c.save()


def rewrite_receipt_with_payment(
    txt_path: str,
    pdf_path: str,
    receipt_no: int,
    business_date: str,
    ts: str,
    cuenta_label: str,
    lines: List[dict],
    subtotal_centavos: int,
    iva_centavos: int,
    total_centavos: int,
    method: str,
    cash_received_centavos: Optional[int] = None,
    change_centavos: Optional[int] = None
) -> None:
    """Reescribe los recibos (TXT y PDF) incluyendo método de pago y vuelto."""
    
    # TXT
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"{BAR_NAME}\n")
        f.write(f"{BAR_SUBTITLE}\n")
        f.write("-" * 32 + "\n")
        f.write(f"Recibo #: {receipt_no}\n")
        f.write(f"Fecha: {business_date}  Hora: {ts.split(' ')[1]}\n")
        f.write(f"Cuenta: {cuenta_label}\n")
        f.write("-" * 32 + "\n")
        for it in lines:
            nombre = it["nombre"][:20]
            qty = it["qty"]
            line_sub = it["line_subtotal_centavos"]
            f.write(f"{qty:>2} x {nombre:<20} {money_from_cents(line_sub):>9}\n")
        f.write("-" * 32 + "\n")
        f.write(f"Subtotal: {money_from_cents(subtotal_centavos)}\n")
        f.write(f"IVA 13%: {money_from_cents(iva_centavos)}\n")
        f.write(f"TOTAL:   {money_from_cents(total_centavos)}\n")
        f.write("-" * 32 + "\n")
        f.write(f"Método de pago: {method}\n")
        if method == "EFECTIVO" and cash_received_centavos is not None and change_centavos is not None:
            f.write(f"Recibido: {money_from_cents(cash_received_centavos)}\n")
            f.write(f"Vuelto:   {money_from_cents(change_centavos)}\n")
        f.write("-" * 32 + "\n")
        f.write("Gracias por su compra.\n")
    
    # PDF
    width = 80 * mm
    base_h = 130 * mm  # Más alto para método de pago
    line_h = 6 * mm
    height = base_h + len(lines) * line_h
    c = canvas.Canvas(pdf_path, pagesize=(width, height))

    x = 6 * mm
    y = height - 10 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, BAR_NAME)
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(x, y, BAR_SUBTITLE)
    y -= 6 * mm

    c.line(x, y, width - x, y)
    y -= 6 * mm

    c.setFont("Helvetica", 9)
    c.drawString(x, y, f"Recibo #: {receipt_no}")
    y -= 5 * mm
    c.drawString(x, y, f"Fecha: {business_date}")
    y -= 5 * mm
    c.drawString(x, y, f"Hora: {ts.split(' ')[1]}")
    y -= 5 * mm
    c.drawString(x, y, f"Cuenta: {cuenta_label}")
    y -= 6 * mm

    c.line(x, y, width - x, y)
    y -= 6 * mm

    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x, y, "Cant  Producto")
    c.drawRightString(width - x, y, "Subtotal")
    y -= 5 * mm

    c.setFont("Helvetica", 8.5)
    for it in lines:
        qty = it["qty"]
        nombre = it["nombre"][:18]
        line_sub = it["line_subtotal_centavos"]
        c.drawString(x, y, f"{qty:>2}  {nombre}")
        c.drawRightString(width - x, y, money_from_cents(line_sub))
        y -= 5 * mm

    y -= 2 * mm
    c.line(x, y, width - x, y)
    y -= 6 * mm

    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Subtotal:")
    c.drawRightString(width - x, y, money_from_cents(subtotal_centavos))
    y -= 5 * mm
    c.drawString(x, y, "IVA 13%:")
    c.drawRightString(width - x, y, money_from_cents(iva_centavos))
    y -= 6 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "TOTAL:")
    c.drawRightString(width - x, y, money_from_cents(total_centavos))
    y -= 8 * mm

    c.setFont("Helvetica", 9)
    c.drawString(x, y, f"Método: {method}")
    y -= 5 * mm
    
    if method == "EFECTIVO" and cash_received_centavos is not None and change_centavos is not None:
        c.drawString(x, y, f"Recibido:")
        c.drawRightString(width - x, y, money_from_cents(cash_received_centavos))
        y -= 5 * mm
        c.drawString(x, y, f"Vuelto:")
        c.drawRightString(width - x, y, money_from_cents(change_centavos))
        y -= 6 * mm

    y -= 4 * mm
    c.setFont("Helvetica", 8.5)
    c.drawString(x, y, "Gracias por su compra.")

    c.showPage()
    c.save()


class POSService:
    """
    Servicio de negocio:
    - Maneja cuentas en memoria (10 slots)
    - Persiste cuentas abiertas en SQLite (open_accounts / open_account_items)
    - Genera recibo PDF+TXT al cerrar cuenta
    - Usuarios/roles (login lo maneja la GUI, aquí solo DB)
    """
    def __init__(self, db: InventarioDB):
        self.db = db
        self.cuentas: Dict[int, Optional[Cuenta]] = {i: None for i in range(1, MAX_CUENTAS + 1)}
        self._load_open_accounts_from_db()

    def _load_open_accounts_from_db(self) -> None:
        rows = self.db.list_open_accounts()
        for r in rows:
            slot = int(r["slot"])
            if slot < 1 or slot > MAX_CUENTAS:
                continue
            cuenta = Cuenta(slot_id=slot, nombre=r["nombre"], opened_date=r["opened_date"])
            items = self.db.list_open_items(slot)
            for it in items:
                pid = int(it["product_id"])
                qty = int(it["qty"])
                if qty > 0:
                    cuenta.items[pid] = qty
            self.cuentas[slot] = cuenta

    def business_date(self) -> str:
        return system_business_date()

    # ---- Usuarios (delegados a DB) ----
    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        return self.db.authenticate_user(username, password)

    def list_users(self):
        return self.db.list_users()

    def create_user(self, username: str, password: str, role: str) -> None:
        self.db.create_user(username, password, role)

    def delete_user(self, username: str) -> None:
        self.db.delete_user(username)

    def set_password(self, username: str, new_password: str) -> None:
        self.db.set_password(username, new_password)

    # ---- Productos CRUD ----
    def create_product(self, nombre: str, tipo: str, precio_colones: float, stock: int) -> int:
        precio_centavos = int(round(precio_colones * 100))
        return self.db.create_product(nombre, tipo, precio_centavos, stock)

    def update_product(self, product_id: int, nombre: str, tipo: str, precio_colones: float, stock: int) -> None:
        precio_centavos = int(round(precio_colones * 100))
        self.db.update_product(product_id, nombre, tipo, precio_centavos, stock)

    def set_stock(self, product_id: int, new_stock: int) -> None:
        self.db.set_stock(product_id, new_stock)

    def adjust_stock(self, product_id: int, delta: int) -> None:
        ok = self.db.adjust_stock(product_id, delta)
        if not ok:
            raise ValueError("No se pudo ajustar stock (quedaría negativo o producto no existe).")

    # ---- Consultas ----
    def list_products(self) -> List[Producto]:
        return self.db.list_products()

    def get_product(self, product_id: int) -> Optional[Producto]:
        return self.db.get_product(product_id)

    def accounts_state(self) -> List[Dict[str, Any]]:
        out = []
        for slot in range(1, MAX_CUENTAS + 1):
            c = self.cuentas[slot]
            if c is None:
                out.append({"slot": slot, "nombre": "", "estado": "LIBRE", "items": 0, "opened_date": ""})
            else:
                out.append({
                    "slot": slot,
                    "nombre": c.nombre,
                    "estado": "VACIA" if c.is_empty() else "CON_ITEMS",
                    "items": sum(c.items.values()),
                    "opened_date": c.opened_date
                })
        return out

    def stale_open_accounts(self) -> List[Tuple[int, str, str]]:
        today = self.business_date()
        stale = []
        for slot, c in self.cuentas.items():
            if c is not None and c.opened_date != today:
                stale.append((slot, c.nombre, c.opened_date))
        return stale

    def clear_open_accounts(self) -> None:
        for slot in self.cuentas:
            self.cuentas[slot] = None
        self.db.clear_all_open_accounts()

    # ---- Cuentas ----
    def open_account(self, slot: int, nombre: str) -> None:
        if slot < 1 or slot > MAX_CUENTAS:
            raise ValueError("Slot inválido (1..10).")
        if self.cuentas[slot] is not None:
            raise ValueError("Ese slot ya está ocupado.")
        if not nombre.strip():
            nombre = f"Mesa {slot}"

        opened_date = self.business_date()
        self.cuentas[slot] = Cuenta(slot, nombre, opened_date)
        self.db.upsert_open_account(slot, nombre, opened_date)

    def add_item(self, slot: int, product_id: int, qty: int) -> None:
        if qty <= 0:
            raise ValueError("Cantidad inválida.")
        cuenta = self.cuentas.get(slot)
        if cuenta is None:
            raise ValueError("No hay cuenta abierta en ese slot.")

        prod = self.db.get_product(product_id)
        if not prod:
            raise ValueError("Producto no existe.")

        if prod.stock < qty:
            raise ValueError(f"Stock insuficiente. Stock actual: {prod.stock}")

        ok = self.db.adjust_stock(product_id, -qty)
        if not ok:
            raise ValueError("No se pudo descontar stock.")

        cuenta.add_item(product_id, qty)
        self.db.upsert_open_item(slot, product_id, cuenta.items.get(product_id, 0))

    def remove_item(self, slot: int, product_id: int, qty: int) -> None:
        if qty <= 0:
            raise ValueError("Cantidad inválida.")
        cuenta = self.cuentas.get(slot)
        if cuenta is None:
            raise ValueError("No hay cuenta abierta en ese slot.")

        ok_remove = cuenta.remove_item(product_id, qty)
        if not ok_remove:
            raise ValueError("No se pudo quitar (producto no está o cantidad inválida).")

        ok_stock = self.db.adjust_stock(product_id, +qty)
        if not ok_stock:
            raise ValueError("No se pudo devolver stock (inconsistencia).")

        self.db.upsert_open_item(slot, product_id, cuenta.items.get(product_id, 0))

    def account_detail(self, slot: int) -> Dict[str, Any]:
        cuenta = self.cuentas.get(slot)
        if cuenta is None:
            raise ValueError("No hay cuenta abierta en ese slot.")

        lines = []
        subtotal = 0
        for pid, qty in cuenta.items.items():
            prod = self.db.get_product(pid)
            if not prod:
                continue
            line_sub = prod.precio_centavos * qty
            subtotal += line_sub
            lines.append({
                "product_id": pid,
                "nombre": prod.nombre,
                "tipo": prod.tipo,
                "qty": qty,
                "unit_price_centavos": prod.precio_centavos,
                "line_subtotal_centavos": line_sub
            })

        iva = int(round(subtotal * IVA_RATE))
        total = subtotal + iva
        return {
            "slot": slot,
            "nombre": cuenta.nombre,
            "opened_date": cuenta.opened_date,
            "lines": lines,
            "subtotal_centavos": subtotal,
            "iva_centavos": iva,
            "total_centavos": total
        }

    def free_empty_account(self, slot: int) -> None:
        cuenta = self.cuentas.get(slot)
        if cuenta is None:
            raise ValueError("No hay cuenta abierta en ese slot.")
        if not cuenta.is_empty():
            raise ValueError("Solo se puede liberar si la cuenta está vacía.")
        self.cuentas[slot] = None
        self.db.delete_open_account(slot)

    def close_account(self, slot: int) -> Dict[str, Any]:
        cuenta = self.cuentas.get(slot)
        if cuenta is None:
            raise ValueError("No hay cuenta abierta en ese slot.")

        if cuenta.is_empty():
            self.cuentas[slot] = None
            self.db.delete_open_account(slot)
            return {"closed": True, "recorded": False, "subtotal_centavos": 0, "iva_centavos": 0, "total_centavos": 0}

        bd = self.business_date()
        detalle = self.account_detail(slot)
        lines = detalle["lines"]
        subtotal = detalle["subtotal_centavos"]
        iva = detalle["iva_centavos"]
        total = detalle["total_centavos"]

        # Distribuir IVA proporcional por línea (para reportes)
        iva_remaining = iva
        for i, item in enumerate(lines):
            line_sub = item["line_subtotal_centavos"]
            if i == len(lines) - 1:
                line_iva = iva_remaining
            else:
                line_iva = int(round(iva * (line_sub / subtotal))) if subtotal > 0 else 0
                line_iva = min(line_iva, iva_remaining)
                iva_remaining -= line_iva

            line_total = line_sub + line_iva
            prod = self.db.get_product(item["product_id"])
            if prod:
                self.db.record_sales_line(
                    business_date=bd,
                    cuenta_label=cuenta.nombre,
                    product=prod,
                    qty=item["qty"],
                    line_subtotal_centavos=line_sub,
                    line_iva_centavos=line_iva,
                    line_total_centavos=line_total
                )

        closed_id = self.db.record_closed_account(
            business_date=bd,
            cuenta_label=cuenta.nombre,
            subtotal_centavos=subtotal,
            iva_centavos=iva,
            total_centavos=total,
            items_json=json.dumps(lines, ensure_ascii=False)
        )

        # Generar recibo (PDF + TXT) y guardar referencia
        receipt_no = self.db.next_receipt_no(bd)
        receipts_dir = os.path.join(app_base_dir(), "receipts", bd)
        os.makedirs(receipts_dir, exist_ok=True)

        base_name = f"recibo_{bd}_{receipt_no:03d}_{safe_filename(cuenta.nombre)}"
        pdf_path = os.path.join(receipts_dir, base_name + ".pdf")
        txt_path = os.path.join(receipts_dir, base_name + ".txt")

        ts = now_ts()
        # Nota: Los recibos se escribirán después con el método de pago
        # Por ahora generamos sin método (se actualizarán en GUI)
        write_receipt_pdf(pdf_path, receipt_no, bd, ts, cuenta.nombre, lines, subtotal, iva, total)
        write_receipt_txt(txt_path, receipt_no, bd, ts, cuenta.nombre, lines, subtotal, iva, total)

        self.db.insert_receipt(bd, receipt_no, cuenta.nombre, closed_id, pdf_path, txt_path)

        # Liberar slot + borrar persistencia de cuenta abierta
        self.cuentas[slot] = None
        self.db.delete_open_account(slot)

        return {
            "closed": True,
            "recorded": True,
            "closed_account_id": closed_id,
            "subtotal_centavos": subtotal,
            "iva_centavos": iva,
            "total_centavos": total,
            "receipt_no": receipt_no,
            "receipt_pdf": pdf_path,
            "receipt_txt": txt_path
        }

    # ---- Reportes / cierre ----
    def daily_report(self, business_date: str) -> Dict[str, Any]:
        sub, iva, tot, cnt = self.db.daily_summary(business_date)
        by_product = self.db.daily_sales_by_product(business_date)
        return {
            "business_date": business_date,
            "subtotal_centavos": sub,
            "iva_centavos": iva,
            "total_centavos": tot,
            "cuentas_cerradas": cnt,
            "ventas_por_producto": by_product
        }

    def list_receipts(self, business_date: str):
        return self.db.list_receipts(business_date)

    def can_close_day(self) -> List[Tuple[int, str]]:
        abiertas_con_items = []
        for slot, c in self.cuentas.items():
            if c is not None and not c.is_empty():
                abiertas_con_items.append((slot, c.nombre))
        return abiertas_con_items

    def close_day(self) -> Dict[str, Any]:
        bd = self.business_date()

        abiertas = self.can_close_day()
        if abiertas:
            raise ValueError("No se puede cerrar el día: hay cuentas con consumo abierto.")

        sub, iva, tot, cnt = self.db.daily_summary(bd)
        self.db.record_closure(bd, sub, iva, tot, cnt)

        # Liberar TODO y limpiar DB de cuentas abiertas
        for slot in self.cuentas:
            self.cuentas[slot] = None
        self.db.clear_all_open_accounts()

        closures_today = self.db.closure_count_for_day(bd)

        return {
            "business_date": bd,
            "subtotal_centavos": sub,
            "iva_centavos": iva,
            "total_centavos": tot,
            "cuentas_cerradas": cnt,
            "closures_count_today": closures_today
        }

    # ---- Control de caja ----
    def get_active_cash_session(self):
        """Obtiene la sesión de caja activa para hoy."""
        bd = self.business_date()
        return self.db.get_active_cash_session(bd)
    
    def open_cash_session(self, opening_amount_colones: float, opened_by: str) -> int:
        """Abre una sesión de caja con monto inicial."""
        bd = self.business_date()
        # Verificar que no haya una sesión activa
        active = self.db.get_active_cash_session(bd)
        if active:
            raise ValueError(f"Ya existe una sesión de caja abierta para {bd}")
        
        opening_centavos = int(opening_amount_colones * 100)
        return self.db.open_cash_session(bd, opening_centavos, opened_by)
    
    def record_payment(self, closed_account_id: int, receipt_no: int, method: str,
                      total_centavos: int, cash_received_centavos: Optional[int],
                      change_centavos: Optional[int], created_by: str) -> int:
        """Registra un pago (método de pago) para una cuenta cerrada."""
        bd = self.business_date()
        
        # Validar método
        if method not in ('EFECTIVO', 'TARJETA', 'SINPE'):
            raise ValueError(f"Método de pago inválido: {method}")
        
        # Para efectivo, validar que recibido >= total
        if method == 'EFECTIVO':
            if cash_received_centavos is None or cash_received_centavos < total_centavos:
                raise ValueError("Monto recibido insuficiente para pago en efectivo")
        
        return self.db.record_payment(bd, closed_account_id, receipt_no, method,
                                      total_centavos, cash_received_centavos,
                                      change_centavos, created_by)
    
    def calculate_expected_cash(self, session_id: int, business_date: str) -> int:
        """Calcula el efectivo esperado en caja (apertura + pagos en efectivo)."""
        # Obtener sesión
        cur = self.db.conn.cursor()
        cur.execute("SELECT opening_amount_centavos FROM cash_sessions WHERE id=?", (session_id,))
        row = cur.fetchone()
        if not row:
            return 0
        
        opening = int(row["opening_amount_centavos"])
        
        # Sumar pagos en efectivo
        cur.execute("""
        SELECT COALESCE(SUM(total_centavos), 0) AS total_efectivo
        FROM payments
        WHERE business_date=? AND method='EFECTIVO';
        """, (business_date,))
        row = cur.fetchone()
        total_efectivo = int(row["total_efectivo"])
        
        return opening + total_efectivo
    
    def close_cash_session(self, counted_cash_colones: float, closed_by: str, notes: str = "") -> Dict[str, Any]:
        """Cierra la sesión de caja activa."""
        bd = self.business_date()
        session = self.db.get_active_cash_session(bd)
        
        if not session:
            raise ValueError("No hay sesión de caja abierta para cerrar")
        
        session_id = int(session["id"])
        counted_centavos = int(counted_cash_colones * 100)
        expected_centavos = self.calculate_expected_cash(session_id, bd)
        
        self.db.close_cash_session(session_id, counted_centavos, expected_centavos, closed_by, notes)
        
        diff_centavos = counted_centavos - expected_centavos
        
        return {
            "session_id": session_id,
            "opening_amount_centavos": int(session["opening_amount_centavos"]),
            "expected_cash_centavos": expected_centavos,
            "counted_cash_centavos": counted_centavos,
            "diff_cash_centavos": diff_centavos,
            "business_date": bd
        }
    
    def cash_report(self, business_date: str) -> Dict[str, Any]:
        """Genera reporte de caja para una fecha."""
        session = self.db.get_active_cash_session(business_date)
        
        # Si no hay sesión, buscar la cerrada del día
        if not session:
            cur = self.db.conn.cursor()
            cur.execute("""
            SELECT * FROM cash_sessions
            WHERE business_date=?
            ORDER BY id DESC LIMIT 1;
            """, (business_date,))
            session = cur.fetchone()
        
        if not session:
            return {
                "has_session": False,
                "business_date": business_date
            }
        
        # Obtener pagos del día
        payments = self.db.get_payments_for_session(business_date)
        
        # Agrupar por método
        efectivo_total = 0
        tarjeta_total = 0
        sinpe_total = 0
        efectivo_count = 0
        tarjeta_count = 0
        sinpe_count = 0
        
        for p in payments:
            total = int(p["total_centavos"])
            if p["method"] == "EFECTIVO":
                efectivo_total += total
                efectivo_count += 1
            elif p["method"] == "TARJETA":
                tarjeta_total += total
                tarjeta_count += 1
            elif p["method"] == "SINPE":
                sinpe_total += total
                sinpe_count += 1
        
        opening = int(session["opening_amount_centavos"])
        expected_cash = opening + efectivo_total
        
        result = {
            "has_session": True,
            "business_date": business_date,
            "session_id": int(session["id"]),
            "is_closed": session["closed_ts"] is not None,
            "opened_by": session["opened_by"],
            "opened_ts": session["opened_ts"],
            "opening_amount_centavos": opening,
            "efectivo_total_centavos": efectivo_total,
            "tarjeta_total_centavos": tarjeta_total,
            "sinpe_total_centavos": sinpe_total,
            "efectivo_count": efectivo_count,
            "tarjeta_count": tarjeta_count,
            "sinpe_count": sinpe_count,
            "expected_cash_centavos": expected_cash,
            "total_ventas_centavos": efectivo_total + tarjeta_total + sinpe_total
        }
        
        if session["closed_ts"]:
            result["closed_by"] = session["closed_by"]
            result["closed_ts"] = session["closed_ts"]
            result["counted_cash_centavos"] = int(session["counted_cash_centavos"]) if session["counted_cash_centavos"] else 0
            result["diff_cash_centavos"] = int(session["diff_cash_centavos"]) if session["diff_cash_centavos"] else 0
            result["notes"] = session["notes"] or ""
        
        return result

    # ---- Export CSV ----
    def export_csv(self, business_date: str, export_dir: str) -> Dict[str, str]:
        os.makedirs(export_dir, exist_ok=True)

        inv_path = os.path.join(export_dir, f"inventario_{business_date}.csv")
        products = self.db.list_products()
        with open(inv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "nombre", "tipo", "precio", "stock", "estado"])
            for p in products:
                estado = "SIN STOCK" if p.stock <= 0 else ("BAJO" if p.stock <= LOW_STOCK_THRESHOLD else "OK")
                w.writerow([p.id, p.nombre, p.tipo, p.precio_centavos / 100, p.stock, estado])

        ventas_path = os.path.join(export_dir, f"ventas_por_producto_{business_date}.csv")
        rows = self.db.daily_sales_by_product(business_date)
        with open(ventas_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["product_id", "nombre", "tipo", "qty_total", "subtotal", "iva", "total"])
            for r in rows:
                w.writerow([
                    r["product_id"],
                    r["product_nombre"],
                    r["product_tipo"],
                    int(r["qty_total"]),
                    int(r["subtotal_total"]) / 100,
                    int(r["iva_total"]) / 100,
                    int(r["total_total"]) / 100
                ])

        cuentas_path = os.path.join(export_dir, f"cuentas_cerradas_{business_date}.csv")
        closed = self.db.list_closed_accounts(business_date)
        with open(cuentas_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "ts", "cuenta", "subtotal", "iva", "total", "items_json"])
            for r in closed:
                w.writerow([
                    r["id"],
                    r["ts"],
                    r["cuenta_label"],
                    int(r["subtotal_centavos"]) / 100,
                    int(r["iva_centavos"]) / 100,
                    int(r["total_centavos"]) / 100,
                    r["items_json"]
                ])

        cierre_path = os.path.join(export_dir, f"cierre_{business_date}.csv")
        sub, iva, tot, cnt = self.db.daily_summary(business_date)
        with open(cierre_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["business_date", "cuentas_cerradas", "subtotal", "iva", "total"])
            w.writerow([business_date, cnt, sub / 100, iva / 100, tot / 100])

        # Export de recibos (para auditoría)
        rec_path = os.path.join(export_dir, f"recibos_{business_date}.csv")
        receipts = self.db.list_receipts(business_date)
        with open(rec_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "ts", "business_date", "receipt_no", "cuenta", "pdf_path", "txt_path"])
            for r in receipts:
                w.writerow([r["id"], r["ts"], r["business_date"], r["receipt_no"], r["cuenta_label"], r["pdf_path"], r["txt_path"]])

        # Export de pagos (métodos de pago)
        payments_path = os.path.join(export_dir, f"payments_{business_date}.csv")
        payments = self.db.get_payments_for_session(business_date)
        with open(payments_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "receipt_no", "method", "total", "cash_received", "change", "created_ts", "created_by"])
            for p in payments:
                w.writerow([
                    p["id"],
                    p["receipt_no"],
                    p["method"],
                    int(p["total_centavos"]) / 100,
                    int(p["cash_received_centavos"]) / 100 if p["cash_received_centavos"] else "",
                    int(p["change_centavos"]) / 100 if p["change_centavos"] else "",
                    p["created_ts"],
                    p["created_by"]
                ])

        # Export de caja (sesiones)
        caja_path = os.path.join(export_dir, f"caja_{business_date}.csv")
        cash_report = self.cash_report(business_date)
        with open(caja_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if cash_report["has_session"]:
                w.writerow(["Campo", "Valor"])
                w.writerow(["Fecha", cash_report["business_date"]])
                w.writerow(["Apertura", cash_report["opening_amount_centavos"] / 100])
                w.writerow(["Ventas Efectivo", cash_report["efectivo_total_centavos"] / 100])
                w.writerow(["Transacciones Efectivo", cash_report["efectivo_count"]])
                w.writerow(["Ventas Tarjeta", cash_report["tarjeta_total_centavos"] / 100])
                w.writerow(["Transacciones Tarjeta", cash_report["tarjeta_count"]])
                w.writerow(["Ventas SINPE", cash_report["sinpe_total_centavos"] / 100])
                w.writerow(["Transacciones SINPE", cash_report["sinpe_count"]])
                w.writerow(["Efectivo Esperado", cash_report["expected_cash_centavos"] / 100])
                w.writerow(["Total Ventas", cash_report["total_ventas_centavos"] / 100])
                if cash_report["is_closed"]:
                    w.writerow(["Efectivo Contado", cash_report["counted_cash_centavos"] / 100])
                    w.writerow(["Diferencia", cash_report["diff_cash_centavos"] / 100])
                    w.writerow(["Notas", cash_report.get("notes", "")])
            else:
                w.writerow(["No hay sesión de caja para esta fecha"])

        return {
            "inventario": inv_path,
            "ventas_por_producto": ventas_path,
            "cuentas_cerradas": cuentas_path,
            "cierre": cierre_path,
            "recibos": rec_path,
            "payments": payments_path,
            "caja": caja_path
        }
