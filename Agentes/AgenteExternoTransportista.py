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

__author__ = 'javier'


# Configuration stuff
hostname = socket.gethostname()
port = 9010

logger = config_logger(level=1)

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteExternoTransportista = Agent('AgenteExternoTransportista',
                       agn.AgenteExternoTransportista,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
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
    reg_obj = agn[AgenteExternoTransportista.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, AgenteExternoTransportista.uri))
    gmess.add((reg_obj, FOAF.name, Literal(AgenteExternoTransportista.name)))
    gmess.add((reg_obj, DSO.Address, Literal(AgenteExternoTransportista.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.AgenteExternoTransportista))

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=AgenteExternoTransportista.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr


@app.route("/comm")
def comunicacion():
    """
       Communication Entrypoint
       """

    global dsGraph
    logger.info('Peticion de informacion recibida')

    message = request.args['content']
    gm = Graph()
    gm.parse(data=message)

    msgdic = get_message_properties(gm)

    gr = None

    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteExternoTransportista.uri, msgcnt=get_count())
    else:
        # El agente centro logistico nos hace request del precio de nuestro transporte
        if msgdic['performative'] == ACL.request:

            content = msgdic['content']
            peso = gm.value(subject=content, predicate=ECSDI.Peso)

            gr = build_message(devolverPrecio(peso),
                               ACL['propose'],
                               sender=AgenteExternoTransportista.uri,
                               msgcnt=get_count())

        # El agentre centro logistico nos informa que nos ha elegido como transportista
        elif msgdic['performative'] == ACL.inform:
            gr = build_message(Graph(), ACL['agree'], sender=AgenteExternoTransportista.uri,
                               msgcnt=get_count())
            logger.info('Pedido entregado')

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml'), 200


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


