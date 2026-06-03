# Manual de Usuario — Rossi Home

---

## Acceso y usuarios

La app tiene tres niveles de acceso:

| Rol | Acceso |
|-----|--------|
| **Admin** | Todo |
| **Local** | Ventas, créditos, precios, catálogo, caja, presupuestos, clientes, pedidos |
| **Vendedor** | Solo nueva venta y ventas |

Al ingresar, podés activar **Face ID / huella** para no tener que escribir la contraseña cada vez.

---

## Sincronización en la nube

El ícono de nube en el encabezado indica el estado de sincronización. Los datos se guardan automáticamente en la nube después de cada cambio. Si entrás desde otro dispositivo, presioná el ícono de nube para traer los datos más recientes.

> **Importante:** Siempre usá la misma URL (la del Worker de Cloudflare) en todos los dispositivos. URLs distintas = datos distintos.

---

## 1. Nueva Venta

**Cómo hacer una venta:**

1. Tocá **+ Nueva Venta**
2. Elegí la fecha y la vendedora
3. Buscá o creá el cliente
   - Podés ingresar el DNI para autocompletar datos
   - O dejarlo como "Consumidor final"
4. Agregá los productos
5. Elegí la forma de pago:
   - **Efectivo** — pago en mano
   - **Transferencias** — Mercado Pago, Prex (FLEX), cuentas de cada vendedora
   - **Tarjeta de crédito** — TC1, TC3, TC6, TC9, TC12 (según cuotas)
   - **Crédito personal (CP)** — cuotas propias con monto y cantidad personalizable
   - **Plan de ahorro** — pagos programados
   - **Mixto** — combinación de métodos
6. Completá la dirección de entrega si corresponde
7. Agregá observaciones si es necesario
8. Confirmá → podés imprimir o compartir por WhatsApp

---

## 2. Ventas

Historial de todas las ventas realizadas.

**Filtros disponibles:**
- Por texto (producto o cliente)
- Por forma de pago
- Por estado de entrega (pendiente / en camino / entregado)
- Por rango de fechas
- Por vendedora

**Acciones por venta:**
- Ver detalle completo
- Cambiar estado de entrega
- Compartir comprobante por WhatsApp
- Exportar listado a CSV

---

## 3. Créditos

Gestión de todos los planes de pago pendientes (crédito personal, plan de ahorro, tarjetas en cuotas).

**Estados:**
- **Anticipo** — se cobró seña, faltan cuotas
- **Pendientes** — cuotas por cobrar
- **Próximas** — vencen en los próximos días
- **Vencidas** — cuotas atrasadas (se muestran en rojo)
- **Cobradas** — crédito cancelado

**Acciones por crédito:**
- Registrar cobro de cuota
- Registrar anticipo
- Refinanciar
- Pausar/reactivar
- Enviar recordatorio por WhatsApp
- Imprimir recibo de crédito
- Exportar a CSV

---

## 4. Lista de Precios

Vista completa del catálogo con precios, costos y márgenes (solo Admin/Local).

**Filtros:**
- Búsqueda por nombre
- Por proveedor
- Por categoría / subcategoría
- Por marca
- Ordenar por: nombre, precio, margen, más vendido

**Acciones:**
- Agregar producto nuevo
- Editar producto (precio, costo, stock, fotos, etc.)
- Mostrar / ocultar producto
- **Actualización masiva de precios** — aumentar o bajar % a un grupo de productos

---

## 5. Catálogo

Vista visual del catálogo para mostrar a clientes. Muestra fotos, precios y estado de stock.

**Modos:** grilla o lista

**Filtros:** nombre, categoría, subcategoría, proveedor, marca, stock disponible/bajo/sin stock/por pedido

---

## 6. Presupuestos

**Dos tipos:**

**A. Con formas de pago** — muestra el precio según cada forma de pago seleccionada (ideal para mostrarle opciones al cliente en el momento)

**B. Tradicional** — presupuesto clásico para imprimir o enviar por PDF

**Estados de presupuesto:**
- Pendiente
- Concretado (se convirtió en venta)
- No concretado
- Vencido

**Desde el presupuesto podés:** enviarlo por WhatsApp, exportarlo a PDF o convertirlo directamente en venta.

---

## 7. Caja

Registro de todos los movimientos de dinero del local.

**Cuentas disponibles:**
- Efectivo
- Mercado Pago
- Prex (FLEX)
- Cuentas de vendedoras (Gabriela, Rosa, Dolores)
- Varios / Sin clasificar

**Tipos de movimiento:**
- Ingreso manual
- Gasto (con foto de comprobante opcional)
- Traspaso entre cuentas
- Cheques

**Otras funciones:**
- **Arqueo** — cierre de caja con conteo físico
- Filtros por cuenta, tipo y fechas
- Búsqueda por concepto
- Datos bancarios por cuenta (CBU, alias) para generar comprobantes

---

## 8. Reportes

Análisis de ventas por período con comparación contra período anterior.

**Secciones:**
- Totales del período
- Comparativa con período anterior
- Por vendedora
- Por forma de pago
- Cuotas vs contado
- Ventas por día
- Top productos más vendidos
- Top clientes por monto
- Listado detallado

**Filtros:** fechas, vendedora, categoría, producto, cliente

Exportar a CSV disponible.

---

## 9. Liquidaciones

Cálculo de comisiones y bonos por vendedora.

**Cómo funciona:**
1. Elegí la vendedora y el período
2. La app calcula las ventas del período
3. Se aplican los bonos por publicaciones en redes y por monto vendido
4. Se genera el recibo de liquidación
5. Se cierra el período

**Configuración (Admin):**
- Monto por publicación
- Ventas mínimas para bono de publicación
- Tramos de comisión: hasta $2,5M / hasta $5M / más de $5M

Exportar a CSV y PDF.

---

## 10. Clientes

Base de datos de todos los clientes.

**Tipos:** Minorista / Mayorista

**Categorías:** VIP / Regular / Inactivo / Moroso

**Datos por cliente:**
- Nombre, apellido, DNI
- Teléfono, dirección
- Historial de compras
- Créditos activos
- Presupuestos pendientes

**Filtros:** nombre, DNI, teléfono, tipo, categoría, estado de crédito

**Acciones:** editar, enviar WhatsApp, ver historial, exportar CSV

---

## 11. Proveedores y Pedidos

### Proveedores

- Alta de proveedores con configuración completa:
  - Tipo: nacional / importado
  - Con o sin IVA
  - Margen de ganancia
  - Porcentaje de tipo de cambio
  - Descuento contado
  - Descuento camión entero
  - Marcas con descuentos en cascada (ej: RHEEM 37,5% / SAIAR 35,5% / SHERMAN 37%+8%)

- **Importar lista de precios** (Excel .xlsx o CSV):
  1. Subís el archivo
  2. La app auto-detecta columnas (nombre, precio, SKU, sección de marca)
  3. Revisás el mapeo de columnas
  4. Si el archivo tiene varias marcas (como RHEEM con RHEEM/SAIAR/SHERMAN), seleccionás la "Columna de sección" para que cada producto tome el descuento correcto automáticamente
  5. Confirmás → los productos se crean o actualizan con precios calculados

- **Recalcular precios** — botón en "Ver productos" del proveedor para recalcular costo y precio de todos los productos con la configuración actual

- **Snapshot** — guarda una copia de seguridad de los productos del proveedor antes de cada importación, con opción de restaurar

### Pedidos

Estados: Solicitado → Confirmado → En camino → Recibido / Cancelado

---

## 12. Mayorista

**Tres secciones:**

**A. Precios Mayorista** — listado de precios para clientes mayoristas, filtrable y exportable

**B. Clientes Mayoristas** — administración de clientes de tipo mayorista

**C. Generar Lista** — armás una lista personalizada de productos para un cliente mayorista específico y podés:
- Enviarla por WhatsApp
- Exportarla a PDF o HTML
- Convertirla directamente en una venta

---

## 13. Mi Local

Información del negocio y herramientas de marketing.

**Datos del local:**
- Nombre, dirección, teléfono, WhatsApp, Instagram, email
- CUIT / Razón social
- CBU y alias de pago (Mercado Pago, etc.)
- Link a Google Maps
- Horarios
- Fotos del local

**Publicaciones para redes sociales:**
Generador de mensajes listos para compartir: "Visitanos", "Oferta", "Horario", etc.

**Plantillas de WhatsApp:**
Mensajes pre-armados con variables: `{nombre}`, `{producto}`, `{precio}`, `{cuotas}`, `{valor_cuota}`

**Metas:**
- Meta de ventas mensual global
- Meta por vendedora
- Seguimiento del progreso

---

## 14. Financiero

Calculadoras y tipo de cambio.

**Tipo de cambio:**
- Dólar blue y oficial BNA (actualización manual)

**10 calculadoras:**

| Calculadora | Para qué sirve |
|-------------|---------------|
| Pesos → USD | Convertir pesos a dólares |
| USD → Pesos | Convertir dólares a pesos |
| Margen | Calcular precio de venta desde costo con margen deseado |
| Descuento | Ver precio final con descuento |
| Actualizar precio | Calcular aumento o baja porcentual |
| Cuota | Calcular valor de cuota según total y cantidad |
| Ganancia | Ver ganancia real entre precio de costo y venta |
| Contado vs TC | Comparar precio contado vs tarjeta |
| Neto por cobro | Ver cuánto te queda después de comisiones |
| Cuotas propias vs TC | Comparar rentabilidad de cuotas propias vs tarjeta |

---

## 15. Admin

Solo para el rol Administrador.

- Gestión de usuarios (altas, roles, contraseñas)
- Estadísticas generales del sistema (productos, ventas, etc.)
- Cambio de contraseña

---

## Backup y seguridad de datos

- Los datos se guardan en la nube automáticamente (Google Apps Script)
- Antes de cada importación de lista, se crea un snapshot automático con opción de restaurar
- Podés exportar ventas, créditos, clientes y otros datos a CSV en cualquier momento

---

## Preguntas frecuentes

**¿Por qué no veo los datos en el celular?**
Verificá que el marcador apunte a la URL del Worker de Cloudflare (`hidden-cloud-2f0f.leandro-rossi.workers.dev`), no a github.io.

**¿Cómo sincronizo entre PC y celular?**
Tocá el ícono de nube en el encabezado para forzar la sincronización. Usá siempre la misma URL.

**¿Cómo importo una lista con varias marcas en un solo Excel?**
La app detecta automáticamente la columna de sección (ej: columna A con "RHEEM TERMOTANQUES", "SAIAR", "SHERMAN") y aplica el descuento de cada marca por fila. Verificá que la "Columna de sección" esté seleccionada correctamente en el mapper.

**¿Los precios importados quedaron mal?**
Usá el botón **"Recalcular precios"** en la pantalla de productos del proveedor (solo funciona si los productos tienen el precio de lista guardado). Si no, eliminá todos los productos del proveedor y re-importá la lista.

**¿Cómo activo Face ID?**
Después de ingresar con usuario y contraseña, la app te ofrece activar el reconocimiento biométrico. Aceptá y la próxima vez te lo va a pedir automáticamente.
