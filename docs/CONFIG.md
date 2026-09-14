# Referencia de `config.toml`

Todos los insumos del LEC Tool se definen en `config.toml`, en la carpeta raíz del repositorio. La herramienta se ejecuta con `python main.py`; opcionalmente `python main.py otro_archivo.toml`.

Convenciones:

- Valores monetarios en millones de dólares ($MM); tasas como decimales (`0.05` = 5 %).
- Las rutas de archivos son relativas a la carpeta donde está `config.toml`.
- "Obligatorio" indica que la corrida se detiene con un mensaje de error si la clave falta. Las claves con valor por defecto pueden omitirse.
- TOML admite `inf` como número (se usa en `spread_tiers`).

## `[run]`

| Clave | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `id` | texto | obligatorio | Identificador de la corrida. Nombra la subcarpeta `outputs/<id>/` y es el prefijo de todos los archivos. No admite `< > : " / \ \| ? *` |
| `output_dir` | texto | `"outputs"` | Carpeta raíz de resultados |
| `show_figures` | booleano | `false` | `true` abre además las figuras en ventanas (la corrida se detiene hasta cerrarlas) |
| `figure_dpi` | entero ≥ 30 | `130` | Resolución de las figuras PNG |

## `[inputs]`

| Clave | Tipo | Requerida cuando | Descripción |
| --- | --- | --- | --- |
| `event_loss_file` | ruta | siempre | CSV con columnas `year` (entero) y `econ_loss` ($MM) |
| `tail_curve_file` | ruta | `lec.hybrid_curve = true` | CSV con columnas `tail_loss` ($MM) y `tail_aep` (tasa anual de excedencia) |
| `ppo_schedule_file` | ruta | existe un instrumento `ppo` | CSV de una fila sin encabezado con `catalogue_length` valores ($MM disponibles por año) |

## `[lec]`

| Clave | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `loss_scale_factor` | número > 0 | `1.0` | Multiplica todas las pérdidas (catálogo histórico y cola probabilística) |
| `freq_scale_factor` | número > 0 | `1.0` | Multiplica todas las tasas de excedencia |
| `hybrid_curve` | booleano | `true` | Combina la curva empírica con la cola probabilística |
| `bootstrap_samples` | entero ≥ 1 | `1000` | Réplicas bootstrap para la banda de confianza |
| `pml_return_periods` | lista de números ≥ 1 | `[200]` | Periodos de retorno (años) para los que se reporta el PML |
| `gap_threshold_fractions` | lista de números > 0 | `[0.25, 0.50, 0.75, 1.00]` | Umbrales de brecha de financiamiento como fracción de la pérdida máxima de la curva LEC |

## `[simulation]`

| Clave | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `catalogue_length` | entero ≥ 1 | obligatorio | Años por catálogo sintético (horizonte) |
| `simulation_number` | entero ≥ 1 | obligatorio | Número de catálogos independientes |
| `random_seed` | entero | (aleatorio) | Semilla de reproducibilidad. Omitir la línea para una corrida no reproducible |
| `displayed_catalogue` | entero | `0` | Índice (0 a `simulation_number - 1`) del catálogo mostrado en las figuras por catálogo |
| `first_year` | entero | año actual + 1 | Año calendario del primer año simulado (solo etiquetas de ejes y reporte) |

## `[fiscal]`

| Clave | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `resp_fiscal` | número en [0, 1] | obligatorio | Proporción de las pérdidas que es responsabilidad fiscal del gobierno |

## `[[strategy.instruments]]`

Un bloque por instrumento; el orden define el orden de apilado en las figuras. Sin bloques, la estrategia no tiene cobertura y el CBA se omite. Un `ppo` exige un `ccf` en la misma estrategia. Los nombres deben ser únicos.

Claves comunes:

| Clave | Tipo | Descripción |
| --- | --- | --- |
| `name` | texto | Etiqueta del instrumento en figuras y reportes |
| `type` | `"insurance"`, `"ppo"`, `"ccf"`, `"ddo"` | Tipo de instrumento |

Parámetros de pago por tipo (obligatorios):

| Tipo | Claves | Descripción |
| --- | --- | --- |
| `insurance` | `attachment_point`, `exhaustion_point`, `ceding_percentage` | Capa [attachment, exhaustion] en $MM y proporción cedida (0-1) |
| `ppo` | (ninguna) | El calendario de disponibilidad se lee de `inputs.ppo_schedule_file` |
| `ccf` | `ccf_maximum`, `ccf_person`, `Pop_exposed` | Techo total ($MM), pago por persona afectada ($) y población expuesta |
| `ddo` | `ddo_threshold`, `ddo_available` | Pérdida que activa el desembolso y pago fijo por activación ($MM) |

Parámetros de costo opcionales (solo usados por el CBA; sobreescriben `[cba.defaults.<type>]` para ese instrumento):

| Tipo | Claves admitidas |
| --- | --- |
| `insurance` | `rate_on_line`, `premium` |
| `ppo` | `commitment_fee_rate`, `loan_interest_rate`, `repayment_years`, `front_end_fee_rate`, `credit_line` |
| `ccf` | `drawdown_fee_rate`, `loan_interest_rate`, `repayment_years`, `grace_period_years` |
| `ddo` | `loan_interest_rate`, `repayment_years` |

La clave antigua `interest_rate` no se acepta; la tasa contractual del préstamo es `loan_interest_rate` y la tasa social de descuento se define en `[cba]`.

## `[risk_reduction]`

| Clave | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `enabled` | booleano | `false` | Activa la reducción ex-ante del riesgo (DRR). Con `false` no se ejecuta ninguna parte de la DRR |
| `discount_rate` | número en [0, 1] | obligatorio si activa | Tasa para anualizar los beneficios de la inversión |
| `investment` | lista de `catalogue_length` números ≥ 0 | obligatorio si activa | Inversión por año ($MM) |
| `benefit_cost_ratio` | lista de `catalogue_length` números ≥ 0 | obligatorio si activa | Relación beneficio-costo de la inversión de cada año |
| `benefit_horizon` | lista de `catalogue_length` números ≥ 0 | obligatorio si activa | Años durante los que cada inversión genera beneficios |

## `[cba]`

| Clave | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `enabled` | booleano | `false` | Activa el análisis costo-beneficio |
| `loss_basis` | `"total"` o `"fiscal"` | `"total"` | Pérdidas usadas por el CBA: económicas totales o multiplicadas por `resp_fiscal` |
| `social_discount_rate` | número en [0, 1] | `0.05` | Tasa social de descuento para valores presentes |
| `indirect_benefit_factor` | número ≥ 0 | `0.10` | Multiplicador de beneficio indirecto sobre los pagos |
| `omv_lambda` | número ≥ 0 | `0.05` | Parámetro de ajuste por riesgo del OMV |
| `legacy_truncation` | booleano | `false` | `true` reproduce el servicio de deuda año a año truncado al horizonte (solo validación) |

### `[cba.defaults.insurance]`, `[cba.defaults.ppo]`, `[cba.defaults.ccf]`, `[cba.defaults.ddo]`

Valores por defecto de los parámetros de costo de cada tipo de instrumento (mismas claves que la tabla de parámetros de costo opcionales). Si una tabla se omite, se usan los valores del paquete `cba` (calibración Honduras). Para `ccf`, `grace_period_years` debe ser menor que `repayment_years`.

### `[cba.cnc]`

Costo Neto Comparado. Si la tabla se omite, el CNC no se calcula.

| Clave | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `enabled` | booleano | `true` | Calcula el CNC |
| `gdp` | número > 0 | obligatorio | PIB de referencia ($MM), denominador de la severidad del evento |
| `base_rate` | número en [0, 1] | obligatorio | Tasa base internacional (SOFR) |
| `sovereign_base_spread` | número en [0, 1] | obligatorio | Spread soberano en condiciones ordinarias |
| `ex_post_term_years` | entero ≥ 1 | `10` | Plazo de la deuda comercial ex-post |
| `spread_tiers` | lista de pares `[umbral, spread]` | valores del paquete | Spread adicional según pérdida del evento / PIB; el umbral del último tramo suele ser `inf` |

## Validaciones

`config_loader.py` detiene la corrida con un mensaje que indica la sección y la clave cuando: falta una clave obligatoria; un valor está fuera de rango; los vectores de la DRR o el calendario PPO no tienen `catalogue_length` valores; `displayed_catalogue` no es menor que `simulation_number`; un instrumento tiene tipo desconocido, nombre repetido o le falta un parámetro de pago; hay un `ppo` sin `ccf`; un archivo de entrada requerido no existe.
