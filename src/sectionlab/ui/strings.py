"""Spanish user-facing text.

This module is the only place UI text lives (spec S16, decision D6): core modules return
stable English codes, and the interface translates them here. Product name `SectionLab` and
unit symbols stay as they are.
"""

from __future__ import annotations

from sectionlab.core.validation import IssueCode

ISSUE_MESSAGES: dict[str, str] = {
    IssueCode.OPEN_CONTOUR.value: (
        "El contorno está abierto: el último vértice debe unirse con el primero."
    ),
    IssueCode.TOO_FEW_VERTICES.value: "Un contorno necesita al menos tres vértices.",
    IssueCode.DUPLICATE_POINTS.value: (
        "Hay vértices en la misma posición: separa o elimina el duplicado."
    ),
    IssueCode.SELF_INTERSECTION.value: (
        "El contorno se cruza a sí mismo: corrige el cruce señalado en el dibujo."
    ),
    IssueCode.ZERO_AREA.value: (
        "El área es nula: los vértices están alineados o el contorno no encierra superficie."
    ),
}

PARAMETER_ERROR_MESSAGES: dict[str, str] = {
    "PARAMETER_NOT_POSITIVE": "Todos los valores deben ser mayores que cero.",
    "SIDES_BELOW_THREE": "Un polígono regular necesita tres lados o más.",
    "WALL_NOT_THINNER_THAN_OUTER": "El espesor de pared deja el hueco sin abertura.",
    "WALL_NOT_THINNER_THAN_RADIUS": "El espesor de pared cierra el hueco interior.",
    "FLANGE_TOO_THICK": "Las alas no dejan altura de alma.",
    "WEB_TOO_WIDE": "El alma es más ancha que el ala.",
    "LEG_NOT_THINNER_THAN_OUTER": "El espesor del ala es mayor que la dimensión de la pieza.",
}

DOCUMENT_ERROR_MESSAGES: dict[str, str] = {
    "UNSUPPORTED_SCHEMA_VERSION": "El archivo fue creado por otra versión de SectionLab.",
    "UNKNOWN_UNIT": "El archivo usa una unidad que esta versión no reconoce.",
    "MISSING_GEOMETRY": "El archivo no contiene la geometría de la sección.",
    "MALFORMED_POINT": "El archivo tiene un vértice ilegible.",
    "MALFORMED_TEMPLATE": "El archivo tiene parámetros de plantilla ilegibles.",
    "MALFORMED_JSON": "El archivo no tiene el formato de un proyecto de SectionLab.",
}

TEMPLATE_LABELS: dict[str, str] = {
    "RECTANGLE": "Rectángulo",
    "RECT_HOLLOW": "Rectángulo hueco",
    "CIRCLE": "Círculo",
    "PIPE": "Tubo circular",
    "TRIANGLE": "Triángulo",
    "POLYGON": "Polígono regular",
    "I_PROFILE": "Perfil I",
    "H_PROFILE": "Perfil H",
    "U_CHANNEL": "Canal U",
    "L_ANGLE": "Ángulo L",
    "T_PROFILE": "Perfil T",
}

PARAMETER_LABELS: dict[str, str] = {
    "b": "Ancho b",
    "h": "Alto h",
    "t": "Espesor t",
    "tw": "Espesor del alma",
    "tf": "Espesor del ala",
    "d": "Diámetro D",
    "n": "Número de lados",
    "r": "Radio circunscrito R",
    "offset": "Desplazamiento del vértice",
}

# Field -> (label, unit symbol). Units are labels only: values are already converted.
RESULT_LABELS: dict[str, tuple[str, str]] = {
    "area": ("Área", "mm²"),
    "perimeter": ("Perímetro", "mm"),
    "cx": ("Centroide X", "mm"),
    "cy": ("Centroide Y", "mm"),
    "ix": ("Inercia Ix", "mm⁴"),
    "iy": ("Inercia Iy", "mm⁴"),
    "ixy": ("Producto Ixy", "mm⁴"),
    "i1": ("Inercia principal I1", "mm⁴"),
    "i2": ("Inercia principal I2", "mm⁴"),
    "principal_angle_deg": ("Ángulo principal", "°"),
    "rx": ("Radio de giro rx", "mm"),
    "ry": ("Radio de giro ry", "mm"),
    "r1": ("Radio de giro r1", "mm"),
    "r2": ("Radio de giro r2", "mm"),
    "sx": ("Módulo elástico Sx", "mm³"),
    "sy": ("Módulo elástico Sy", "mm³"),
    "x_min": ("X mínimo", "mm"),
    "x_max": ("X máximo", "mm"),
    "y_min": ("Y mínimo", "mm"),
    "y_max": ("Y máximo", "mm"),
}

UI: dict[str, str] = {
    "window_title": "SectionLab",
    "calculate": "Calcular",
    "save": "Guardar proyecto",
    "open": "Abrir proyecto",
    "export_csv": "Exportar CSV",
    "copy_results": "Copiar resultados",
    "settings": "Configuración",
    "active_unit": "Unidad activa",
    "decimals": "Decimales visibles",
    "undo": "Deshacer",
    "redo": "Rehacer",
    "delete_vertex": "Eliminar vértice",
    "add_vertex": "Insertar vértice",
    "template_mode": "Plantilla",
    "free_mode": "Nueva geometría libre",
    "vertex_table": "Vértices",
    "contour": "Contorno",
    "outer_contour": "Exterior",
    "inner_contour": "Interior",
    "index": "N°",
    "results": "Resultados",
    "parameters": "Parámetros",
    "property": "Propiedad",
    "value": "Valor",
    "unit": "Unidad",
    "ortho": "Ortogonal",
    "dimensions": "Cotas",
    "dimensions_tip": "Muestra las cotas que hayas colocado",
    "undo_dimension": "cota",
    "undo_dimension_add": "agregar cota",
    "undo_dimension_delete": "eliminar cota",
    "dimension_tool": "Acotar",
    "dimension_tool_tip": (
        "Clic en una referencia y luego en otra; el tercer clic coloca la cota (Esc cancela)"
    ),
    "dimension_tool_first": "Acotar: elige el primer punto o una línea",
    "dimension_tool_second": "Acotar: elige el segundo punto",
    "dimension_tool_place": "Acotar: mueve el cursor y haz clic para colocar la cota",
    "guides": "Líneas de referencia",
    "guides_tip": "Muestra cuándo el cursor comparte la X o la Y con un vértice o un punto medio",
    "dimensions_hint": "Doble clic sobre una cota para cambiarla",
    "segment_selected_hint": (
        "Línea seleccionada: acótala con la herramienta Acotar para escribir su largo"
    ),
    "dimension_placed": "Cota colocada: doble clic sobre el número para cambiarlo",
    "dimension_needs_section": "Dibuja o elige una sección antes de acotar",
    "dimensions_dropped": "cotas eliminadas: su vértice ya no existe",
    "convert_free": "Convertir a geometría libre",
    "convert_free_tip": "Mantiene el contorno y entrega los vértices para editarlos uno a uno",
    "converted_free": "Geometría libre: edita los vértices o sus cotas",
    "undo_convert": "convertir a geometría libre",
    "panel_left": "Mover a la izquierda",
    "panel_right": "Mover a la derecha",
    "panel_float": "Separar de la ventana",
    "panel_dock": "Volver a la ventana",
    "panel_move_tip": "Arrastra este panel a un costado, o doble clic para separarlo",
    "panel_hide": "Ocultar este panel",
    "menu_help": "Ayuda",
    "check_updates": "Buscar actualizaciones",
    "about": "Acerca de SectionLab",
    "update_available": "Hay una versión nueva",
    "update_now": "Actualizar",
    "update_later": "Más tarde",
    "up_to_date": "Tienes la última versión",
    "checking_in_flight": "Ya hay una comprobación de actualizaciones en curso",
    "update_state_never": "Actualizaciones: sin comprobar todavía",
    "update_state_offered": "Actualizaciones: hay una versión nueva",
    "update_state_up_to_date": "Actualizaciones: al día",
    "update_state_failed": "Actualizaciones: la comprobación falló",
    "check_log_hint": "Detalle en",
    "checking_updates": "Buscando actualizaciones…",
    "version_label": "Versión",
    "about_license": "Gratis para uso personal y no comercial",
    "update_downloading": "Descargando",
    "update_applying": "Aplicando la actualización…",
    "update_ready": "Actualización aplicada",
    "update_restart_question": "¿Reiniciar ahora para usar la versión nueva?",
    "update_unsaved": "Guarda tu trabajo antes de reiniciar",
    "update_failed": "No se pudo actualizar",
    "update_done": "Actualización aplicada: reinicia para usar la versión nueva",
    "update_needs_installer": "Esa versión trae cambios de base y necesita el instalador",
    "update_restart_title": "Reiniciar para actualizar",
    "restart_now": "Reiniciar ahora",
    "restart_later": "Más tarde",
    "installer_ready": "El instalador se descargó en",
    "installer_close_hint": "SectionLab se cerrará y el instalador continuará solo",
    "snap_endpoint": "Extremo",
    "snap_intersection": "Intersección",
    "snap_midpoint": "Punto medio",
    "snap_center": "Centro",
    "snap_perpendicular": "Perpendicular",
    "invalid_title": "No se puede calcular",
    "invalid_hint": "Corrige la geometría y vuelve a intentarlo.",
    "save_failed": "No se pudo guardar el proyecto",
    "open_failed": "No se pudo abrir el proyecto",
    "no_results": "Calcula la sección para ver sus propiedades.",
    "vertex_list": "Lista de vértices",
    "apply": "Aplicar",
    "cancel": "Cancelar",
    "close": "Cerrar",
    "ready": "Dibuja el contorno o elige una plantilla.",
    "menu_file": "Archivo",
    "menu_edit": "Edición",
    "menu_view": "Ver",
    "menu_settings": "Configuración",
    "menu_help": "Ayuda",
    "quit": "Salir",
    "zoom_in": "Acercar",
    "zoom_out": "Alejar",
    "zoom_fit": "Ajustar a la vista",
    "main_toolbar": "Principal",
    "calculated_ready": "Listo para calcular",
    "applied": "Plantilla aplicada",
    "calculated": "Resultados actualizados",
    "saved": "Proyecto guardado",
    "free_started": (
        "Geometría libre: clic para añadir vértices · clic en el primero, botón derecho o Enter para cerrar"
    ),
    "short_calculate": "Calcular",
    "short_open": "Abrir",
    "short_save": "Guardar",
    "short_csv": "CSV",
    "short_undo": "Deshacer",
    "short_redo": "Rehacer",
    "short_insert": "Insertar",
    "short_delete": "Borrar",
    "short_ortho": "Orto",
    "short_measure": "Acotar",
    "short_snap": "Guías",
    "short_zoom_in": "Acercar",
    "short_zoom_out": "Alejar",
    "short_fit": "Ajustar",
    "short_theme": "Tema",
    "short_settings": "Opciones",
    "panels": "Paneles",
    "panels_tip": "Muestra u oculta los paneles (F9); arrástralos para moverlos",
    "panels_all": "Mostrar todos los paneles",
    "panels_hidden_hint": "Paneles ocultos · F9 o Ver → Paneles los recupera",
    "hide_panel": "Ocultar panel",
    "hint_navigate": "Rueda: acercar/alejar · botón central: desplazar · doble clic central: ajustar",
    "theme": "Tema",
    "theme_dark": "Oscuro",
    "theme_light": "Claro",
}

_GENERIC_ERROR = "Ocurrió un problema que esta versión no reconoce."


def message_for(code: str) -> str:
    """Spanish explanation of a blocking validation issue."""
    try:
        return ISSUE_MESSAGES[code]
    except KeyError as error:
        raise KeyError(f"unknown validation code: {code}") from error


def label_for(key: str) -> str:
    """Spanish label for a template kind, a template parameter or a UI key."""
    for table in (TEMPLATE_LABELS, PARAMETER_LABELS, UI):
        if key in table:
            return table[key]
    raise KeyError(f"unknown label key: {key}")


def result_label(field: str) -> tuple[str, str]:
    """Spanish label and unit symbol for one calculated property."""
    try:
        return RESULT_LABELS[field]
    except KeyError as error:
        raise KeyError(f"unknown result field: {field}") from error


DIMENSION_MESSAGES: dict[str, str] = {
    "closing_segment": "El segmento de cierre no se acota: su largo depende de los demás",
    "slanted_segment": "Solo se acota el ancho o el alto de un segmento recto",
    "non_positive": "La cota debe ser mayor que cero",
    "unchanged": "La cota ya tiene ese valor",
    "out_of_range": "Ese segmento no existe en el contorno",
    "too_few_vertices": "Hacen falta al menos tres vértices para acotar",
    "not_a_number": "Escribe un número, por ejemplo 120.5",
    "read_only": "Esta sección viene de una plantilla: cámbiala en sus parámetros",
    "segment_not_editable": "Solo una línea recta horizontal o vertical acepta una longitud escrita",
    "segment_not_dimensioned": "Esa línea no tiene cota: acótala primero con la herramienta Acotar",
    "unchanged_anchors": "Esa cota no define una distancia: elige dos referencias distintas",
    "not_drivable": "Esa cota es de referencia: ninguna medida de la sección depende de ella",
    "unknown_kind": "Esa cota no se puede editar",
    "no_template_driver": "Esa cota no depende de ningún parámetro de la plantilla",
    "FLANGE_TOO_THICK": "Las alas no dejan altura de alma",
    "WEB_TOO_WIDE": "El alma es más ancha que el ala",
    "PARAMETER_NOT_POSITIVE": "Todos los valores deben ser mayores que cero",
    "SIDES_BELOW_THREE": "Un polígono regular necesita tres lados o más",
    "WALL_NOT_THINNER_THAN_OUTER": "El espesor de pared deja el hueco sin abertura",
    "WALL_NOT_THINNER_THAN_RADIUS": "El espesor de pared cierra el hueco interior",
    "LEG_NOT_THINNER_THAN_OUTER": "El espesor del ala es mayor que la dimensión de la pieza",
}


def dimension_message(code: str) -> str:
    """Spanish text for a refused dimension edit (spec S3)."""
    return DIMENSION_MESSAGES.get(code, _GENERIC_ERROR)


UPDATE_MESSAGES: dict[str, str] = {
    "check_failed": "No se pudo comprobar si hay actualizaciones",
    "malformed_release": "La respuesta del servidor no se pudo leer",
    "download_failed": "La descarga se interrumpió; no se cambió nada",
    "digest_mismatch": "El archivo descargado no coincide con su suma de verificación",
    "invalid_archive": "El archivo no contiene la aplicación",
    "install_failed": "No se pudo reemplazar la aplicación; se restauró la anterior",
    "not_installed": "No se encontró la carpeta de instalación",
    "no_asset": "Esa versión no publica un parche de código",
}


def update_message(code: str) -> str:
    """Spanish text for a failed update step (spec S7)."""
    return UPDATE_MESSAGES.get(code, _GENERIC_ERROR)


def error_message(code: str) -> str:
    """Spanish text for any core error code, with a generic fallback for unknown codes."""
    for table in (ISSUE_MESSAGES, PARAMETER_ERROR_MESSAGES, DOCUMENT_ERROR_MESSAGES):
        if code in table:
            return table[code]
    return _GENERIC_ERROR
