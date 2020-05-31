# -*- coding: utf-8 -*-
"""
Created on Fri Dec 27 15:58:13 2013

Esqueleto de agente usando los servicios web de Flask

/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente

Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente

Asume que el agente de registro esta en el puerto 9000

@author: javier
"""

from multiprocessing import Process, Queue
import socket

from rdflib import Namespace, Graph, Literal, XSD, logger
from flask import Flask, request
from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.Logging import config_logger
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.OntoNamespaces import DSO, ECSDI, ACL
from rdflib.namespace import RDF, FOAF

__author__ = 'Miguel'

# Configuration stuff
hostname = socket.gethostname()
port = 9030

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteNegociadorTiendasExternas = Agent('AgenteNegociadorTiendasExternas',
                                        agn.AgenteNegociadorTiendasExternas,
                                        'http://%s:%d/comm' % (hostname, port),
                                        'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.AgenteDirectorio,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)

# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


def get_count():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt


def register():
    global mss_cnt
    logger.info("Nos registramos")
    gmess = Graph()
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    reg_obj = agn[AgenteNegociadorTiendasExternas.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, AgenteNegociadorTiendasExternas.uri))
    gmess.add((reg_obj, FOAF.name, Literal(AgenteNegociadorTiendasExternas.name)))
    gmess.add((reg_obj, DSO.Address, Literal(AgenteNegociadorTiendasExternas.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.AgenteExternoTransportista))

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=AgenteNegociadorTiendasExternas.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr


@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    global dsGraph
    logger.info('Peticion de nuevo producto externo recivida')

    message = request.args['content']
    gm = Graph()
    gm.parse(data=message)

    msgdic = get_message_properties(gm)

    gr = None

    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteNegociadorTiendasExternas.uri,
                           msgcnt=get_count())
    else:
        # Se ha vendido un producto de una tienda externa
        # AgenteCompra --> AgenteNegociadorTiendasExternas --> TiendaExterna
        if msgdic['performative'] == ACL.request:
            content = msgdic['content']

            producto = gm.value(subject=content, predicate=ECSDI.Producto)
            modelo = gm.value(subject=content, predicate=ECSDI.Modelo)
            marca = gm.value(subject=content, predicate=ECSDI.Marca)
            tienda = gm.value(subject=content, predicate=ECSDI.TiendaOrigen)

            #Tramitar Pago a Tienda Externa

            gr = build_message(enviarMsgATiendaExterna(modelo, marca),
                               ACL['inform'],
                               sender=AgenteNegociadorTiendasExternas.uri,
                               msgcnt=get_count(),
                               receiver=tienda)


        # Una tienda externa quiere añadir un producto a nuestra tienda
        elif msgdic['performative'] == ACL.inform:
            content = msgdic['content']
            new = {}  # nuevo producto

            producto = gm.value(subject=content, predicate=ECSDI.Producto)
            new['producto'] = producto
            modelo = gm.value(subject=content, predicate=ECSDI.Modelo)
            new['modelo'] = modelo
            marca = gm.value(subject=content, predicate=ECSDI.Marca)
            new['marca'] = marca
            precio = gm.value(subject=content, predicate=ECSDI.Precio)
            new['precio'] = precio
            tiendaOrigen = msgdic['sender']
            new['tiendaOrigen'] = tiendaOrigen

            ok = anadirProductosTiendaExterna(**new)

            if ok:
                gr = build_message(gr, perf=ACL['inform-done'], sender=AgenteNegociadorTiendasExternas.uri,
                                   msgcnt=get_count(), receiver=tiendaOrigen)
            else:
                gr = build_message(Graph(), ACL['not-understood'], sender=AgenteNegociadorTiendasExternas.uri,
                                   msgcnt=get_count())

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml'), 200


def anadirProductosTiendaExterna(producto=None, modelo=None, marca=None, precio=0.0, tiendaOrigen=None):
    graph = Graph()
    ontologyFile = open('../data/productos')
    graph.parse(ontologyFile, format='turtle')

    if producto is not None and modelo is not None and marca is not None:
        query = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX default: <http://www.semanticweb.org/migue/ontologies/2020/4/ecsdi-practica-ontologia#>
        INSERT INTO Productos VALUES ("""

        query += producto + """, """
        query += modelo + """, """
        query += marca + """, """
        query += str(precio) + """, """
        query += tiendaOrigen + """);"""

        gquery = graph.query(query)

        return True
    else:
        # gr = build_message(Graph(), ACL['not-understood'], sender=AgenteNegociadorTiendasExternas.uri, msgcnt=get_count())
        return False


def enviarMsgATiendaExterna(modelo, marca):
    g = Graph()
    prod = ECSDI.Producto

    g.add((prod, RDF.Type, ECSDI.Producto))
    g.add((prod, ECSDI.Modelo, Literal(modelo)))
    g.add((prod, ECSDI.Marca, Literal(marca)))

    return g

@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')
