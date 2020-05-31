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

from rdflib import Namespace, Graph, Literal
from flask import Flask, request
from AgentUtil.ACLMessages import get_message_properties, build_message, send_message

from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.OntoNamespaces import DSO, ECSDI, ACL
from rdflib.namespace import RDF, FOAF

__author__ = 'Miguel'


# Configuration stuff
hostname = socket.gethostname()
port = 9031

logger = config_logger(level=1)

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteExternoTiendaExterna = Agent('AgenteExternoTiendaExterna',
                       agn.AgenteExternoTiendaExterna,
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
    reg_obj = agn[AgenteExternoTiendaExterna.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, AgenteExternoTiendaExterna.uri))
    gmess.add((reg_obj, FOAF.name, Literal(AgenteExternoTiendaExterna.name)))
    gmess.add((reg_obj, DSO.Address, Literal(AgenteExternoTiendaExterna.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.AgenteExternoTiendaExterna))

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=AgenteExternoTiendaExterna.uri,
                      receiver=AgenteDirectorio.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        AgenteDirectorio.address)
    mss_cnt += 1

    return gr


@app.route("/comm")
def comunicacion():
    """
    Communication Entrypoint
    """

    global dsGraph
    logger.info('Aviso a Tienda Externa de Compra Realizada')

    message = request.args['content']
    gm = Graph()
    gm.parse(data=message)

    msgdic = get_message_properties(gm)

    gr = None

    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteExternoTiendaExterna.uri, msgcnt=get_count())
    else:
        # El AgenteNegociadorTiendasExternas nos informa de que ha habido una compra de uno de nuestros productos
        if msgdic['performative'] != ACL.inform:
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteExternoTiendaExterna.uri, msgcnt=get_count())
        else:
            procesarCompra()


def procesarCompra():
    return 0

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


def devolverPrecio(peso):
    g = Graph()
    transportista = ECSDI.Transportista

    precio = peso * 3
    g.add((transportista, RDF.Type, ECSDI.Transportista))
    g.add((transportista, ECSDI.Nombre, Literal('Pedro')))
    g.add((transportista, ECSDI.Precio, Literal(precio)))

    return g


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


