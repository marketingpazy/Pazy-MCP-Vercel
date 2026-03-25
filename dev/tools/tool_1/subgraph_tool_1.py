from __future__ import annotations

from langgraph.graph import StateGraph, END

from dev.tools.tool_1.nodes.tratar_datos import tratar_datos
from dev.tools.tool_1.nodes.llamada_api import llamada_api
from dev.tools.tool_1.nodes.respuesta_pricing import normalizar_respuesta_pricing

def create_pricing_subgraph():
    builder = StateGraph(dict)

    builder.add_node("tratar_datos", tratar_datos)
    builder.add_node("llamada_api", llamada_api)
    builder.add_node("formatear_respuesta_ui", normalizar_respuesta_pricing)
    
    builder.set_entry_point("tratar_datos")
    builder.add_edge("tratar_datos", "llamada_api")
    builder.add_edge("llamada_api", "formatear_respuesta_ui")
    builder.add_edge("formatear_respuesta_ui", END)

    return builder.compile()
