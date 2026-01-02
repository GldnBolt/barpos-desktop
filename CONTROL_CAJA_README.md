# Sistema de Control de Caja y Métodos de Pago

## 📋 Funcionalidades Implementadas

### 1. **Métodos de Pago**
Al cerrar una cuenta se captura el método de pago:
- 💵 **EFECTIVO**: Captura monto recibido y calcula vuelto automáticamente
- 💳 **TARJETA**: Registra pago sin necesidad de vuelto
- 📱 **SINPE**: Registra pago sin necesidad de vuelto

### 2. **Sesiones de Caja**
Control completo del flujo de efectivo diario:

#### Apertura de Caja (🔓)
- Se registra el monto inicial en caja (ej: ₡20,000)
- Solo se permite una sesión activa por día (business_date)
- Cualquier usuario puede abrir caja

#### Cierre de Caja (🔒)
- Solo usuarios **ADMIN** pueden cerrar caja
- Calcula automáticamente el efectivo esperado:
  ```
  Efectivo esperado = Monto de apertura + Total de ventas en EFECTIVO
  ```
- Se ingresa el efectivo contado físicamente
- Calcula diferencia: `Contado - Esperado`
  - **Verde** (positivo): Hay más dinero del esperado
  - **Rojo** (negativo): Falta dinero
- Permite agregar notas opcionales (ej: "Faltaron ₡500 por cambio dado de más")

### 3. **Flujo de Trabajo**

#### Inicio del Día
1. **Login** con usuario y contraseña
2. **Apertura de caja** desde el tab "Reportes / Recibos"
   - Botón: 🔓 Apertura Caja
   - Ingresar monto inicial (predeterminado: ₡20,000)
3. El sistema muestra el estado: `🔓 CAJA ABIERTA`

#### Durante el Día
1. **Abrir mesas** y agregar productos desde el catálogo táctil
2. **Cobrar y cerrar cuentas** (botón "Cobrar"):
   - Primero valida que haya caja abierta (si no, ofrece abrirla)
   - Genera el recibo temporal
   - **Captura método de pago** con dialog táctil:
     - Si es EFECTIVO: muestra keypad para ingresar monto recibido
     - Calcula vuelto en tiempo real
     - Valida que el monto recibido sea suficiente
   - Registra el pago en la base de datos
   - **Regenera los recibos** (TXT y PDF) con información completa del pago
   - Ofrece imprimir el ticket inmediatamente

#### Cierre del Día
1. Ir al tab **"Reportes / Recibos"**
2. Hacer clic en **💰 Reporte Caja** para ver resumen:
   ```
   ═══ REPORTE DE CAJA ═══
   
   Apertura: ₡20,000.00
   
   VENTAS:
     💵 Efectivo: ₡15,600.00 (8 ventas)
     💳 Tarjeta: ₡8,900.00 (3 ventas)
     📱 SINPE: ₡6,000.00 (2 ventas)
   
   EFECTIVO ESPERADO: ₡35,600.00
   (Apertura + Efectivo)
   ```
3. Hacer clic en **🔒 Cierre Caja** (solo ADMIN):
   - Muestra efectivo esperado: ₡35,600.00
   - Ingresar efectivo contado (ej: ₡35,500.00)
   - Muestra diferencia en tiempo real: -₡100.00 (rojo)
   - Agregar notas opcionales
   - Confirmar cierre
4. El sistema registra la sesión de caja como cerrada

### 4. **Base de Datos**

#### Tabla `cash_sessions`
```sql
CREATE TABLE IF NOT EXISTS cash_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_date TEXT NOT NULL,
    opening_amount_centavos INTEGER NOT NULL,
    opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
    opened_by TEXT,
    closed_at TEXT,
    closed_by TEXT,
    counted_cash_centavos INTEGER,
    expected_cash_centavos INTEGER,
    diff_cash_centavos INTEGER,
    notes TEXT,
    UNIQUE(business_date)
)
```

#### Tabla `payments`
```sql
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    closed_account_id INTEGER NOT NULL,
    receipt_no TEXT NOT NULL,
    method TEXT NOT NULL CHECK(method IN ('EFECTIVO','TARJETA','SINPE')),
    total_centavos INTEGER NOT NULL,
    cash_received_centavos INTEGER,
    change_centavos INTEGER,
    created_ts TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    FOREIGN KEY(closed_account_id) REFERENCES closed_accounts(id)
)
```

### 5. **Recibos con Información de Pago**

#### Formato TXT (80mm térmico)
```
========================================
           BAR "LA CHOZA"
========================================
Recibo #: 2026-01-02_003

Mesa: Mesa 1
Fecha: 2026-01-02
Hora: 14:35:22
Cajero: jenny
----------------------------------------

2 x Imperial 8oz           ₡3,000.00
1 x Nachos                 ₡2,500.00

----------------------------------------
Subtotal:                  ₡5,500.00
IVA (13%):                   ₡715.00
TOTAL:                     ₡6,215.00
========================================

MÉTODO DE PAGO: EFECTIVO
Recibido:                 ₡10,000.00
Vuelto:                    ₡3,785.00

========================================
    ¡GRACIAS POR SU VISITA!
========================================
```

#### Formato PDF
Similar al TXT pero formateado para PDF 80mm con ReportLab.

### 6. **Exportación CSV**

El sistema exporta **7 archivos CSV** con toda la información del día:

1. `inventario_YYYY-MM-DD.csv`: Stock de productos
2. `ventas_por_producto_YYYY-MM-DD.csv`: Ventas agrupadas por producto
3. `cuentas_cerradas_YYYY-MM-DD.csv`: Todas las cuentas cobradas
4. `cierre_YYYY-MM-DD.csv`: Información del cierre diario
5. `recibos_YYYY-MM-DD.csv`: Lista de recibos generados
6. **`payments_YYYY-MM-DD.csv`**: Métodos de pago por recibo
   - Columnas: id, receipt_no, method, total, cash_received, change, created_ts, created_by
7. **`caja_YYYY-MM-DD.csv`**: Resumen de sesión de caja
   - Columnas: business_date, opening, efectivo_ventas, tarjeta_ventas, sinpe_ventas, efectivo_count, tarjeta_count, sinpe_count, expected_cash, counted_cash, diff_cash, notes

### 7. **Interfaz de Usuario**

#### Tab "Reportes / Recibos"
```
┌───────────────────────────────────────────────────────────────┐
│ Fecha: [2026-01-02] [Cargar] [Exportar CSV] [Usuarios]       │
│ [💰 Reporte Caja] [🔒 Cierre Caja] [🔓 Apertura Caja] [Cierre]│
├───────────────────────────────────────────────────────────────┤
│ 🔓 CAJA ABIERTA | Apertura: ₡20,000.00 | Usuario: jenny     │
├───────────────────────────────────────────────────────────────┤
│ Cuentas cerradas: 13 | Subtotal: ₡28,450.00 | ...            │
└───────────────────────────────────────────────────────────────┘
```

#### Dialog de Método de Pago (PaymentMethodDialog)
```
┌─────────────────────────────────────┐
│       Total a pagar: ₡6,215.00      │
│                                     │
│   Selecciona método de pago:       │
│                                     │
│  [💵 EFECTIVO] [💳 TARJETA] [📱 SINPE] │
│                                     │
│            [Cancelar]               │
└─────────────────────────────────────┘
```

#### Dialog de Pago en Efectivo (CashPaymentDialog)
```
┌─────────────────────────────────────┐
│       Total: ₡6,215.00              │
│                                     │
│      Monto recibido:                │
│      [ 10000 ]                      │
│                                     │
│   Vuelto: ₡3,785.00 (verde)        │
│                                     │
│   [7] [8] [9]                       │
│   [4] [5] [6]                       │
│   [1] [2] [3]                       │
│   [C] [0] [←]                       │
│                                     │
│  [Cancelar]    [Confirmar]          │
└─────────────────────────────────────┘
```

### 8. **Validaciones Implementadas**

✅ No se puede cobrar sin caja abierta (ofrece abrirla)
✅ No se puede abrir caja duplicada para el mismo día
✅ Solo ADMIN puede cerrar caja
✅ En pago EFECTIVO, valida que el monto recibido >= total
✅ Calcula vuelto automáticamente en tiempo real
✅ No permite cerrar día con cuentas abiertas
✅ Todos los montos se almacenan en centavos (int) para evitar errores de redondeo
✅ Los recibos se regeneran con información de pago después de capturarlo

### 9. **Testing Recomendado**

#### Secuencia de Prueba Completa
1. **Login** con usuario (ej: jenny/123)
2. **Ir al tab Reportes** → Clic en 🔓 Apertura Caja → Ingresar ₡20,000 → Confirmar
3. **Ir al tab Mesas** → Seleccionar Mesa 1 → Abrir Mesa → Nombre: "Juan"
4. **Agregar productos** desde catálogo táctil (ej: 2x Imperial, 1x Nachos)
5. **Cobrar** → Confirmar → Seleccionar EFECTIVO
6. **Ingresar recibido** (ej: ₡10,000) → Ver vuelto calculado → Confirmar
7. **Verificar recibo** impreso/guardado con método de pago
8. **Abrir otra cuenta** (Mesa 2) → Agregar productos → Cobrar con TARJETA
9. **Abrir otra cuenta** (Mesa 3) → Agregar productos → Cobrar con SINPE
10. **Ir a Reportes** → Clic en 💰 Reporte Caja → Verificar totales por método
11. **Login como ADMIN** (admin/admin)
12. **Cierre de Caja** → Ingresar contado (ej: ₡35,600) → Verificar diferencia → Confirmar
13. **Exportar CSV** → Verificar que se generen 7 archivos incluyendo payments_*.csv y caja_*.csv
14. **Abrir recibos TXT** → Verificar que muestren método de pago y vuelto

## 🎯 Características Destacadas

- **Touch-friendly**: Todos los dialogs tienen botones grandes optimizados para pantallas táctiles
- **Keypad numérico**: Entrada táctil de montos sin necesidad de teclado físico
- **Cálculo en tiempo real**: El vuelto se actualiza mientras se ingresa el monto
- **Recibos completos**: Incluyen método de pago, monto recibido y vuelto
- **Exportación completa**: 7 archivos CSV con toda la información financiera
- **Validación exhaustiva**: Previene errores comunes (caja cerrada, montos insuficientes, etc.)
- **Auditoría completa**: Registro de quién abrió/cerró caja, timestamps, diferencias
- **Sin errores de redondeo**: Toda la aritmética se hace en centavos (enteros)

## 🚀 Mejoras Futuras Sugeridas

- [ ] Dashboard visual con gráficos de ventas por método
- [ ] Historial de sesiones de caja (últimos 30 días)
- [ ] Alertas automáticas si la diferencia de caja supera un umbral
- [ ] Soporte para múltiples monedas
- [ ] Integración con impresoras térmicas específicas
- [ ] Backup automático de base de datos al cerrar caja
- [ ] Reportes de propinas por cajero
- [ ] Sistema de descuentos y promociones

## 📝 Notas Técnicas

- **Backend**: `pos_core.py` - InventarioDB y POSService
- **Frontend**: `pos_gui.py` - Tkinter touch UI
- **Base de datos**: SQLite con `row_factory = sqlite3.Row`
- **Recibos**: ReportLab (PDF) + TXT plano para impresoras térmicas
- **IVA**: 13% fijo sobre todos los productos
- **Resolución**: Optimizado para 1920x1080
