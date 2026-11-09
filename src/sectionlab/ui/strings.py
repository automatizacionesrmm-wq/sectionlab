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
    "free_started": "Geometría libre: haz clic para añadir vértices",
    "short_calculate": "Calcular",
    "short_open": "Abrir",
    "short_save": "Guardar",
    "short_csv": "CSV",
    "short_undo": "Deshacer",
    "short_redo": "Rehacer",
    "short_insert": "Insertar",
    "short_delete": "Borrar",
    "short_ortho": "Orto",
    "short_zoom_in": "Acercar",
    "short_zoom_out": "Alejar",
    "short_fit": "Ajustar",
    "short_theme": "Tema",
    "short_settings": "Opciones",
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


def error_message(code: str) -> str:
    """Spanish text for any core error code, with a generic fallback for unknown codes."""
    for table in (ISSUE_MESSAGES, PARAMETER_ERROR_MESSAGES, DOCUMENT_ERROR_MESSAGES):
        if code in table:
            return table[code]
    return _GENERIC_ERROR
