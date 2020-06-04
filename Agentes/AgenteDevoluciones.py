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
import sys
from multiprocessing import Process, Queue
import socket

import datetime
from rdflib import Namespace, Graph, Literal, XSD, URIRef
from flask import Flask, request
from AgentUtil.ACLMessages import get_message_properties, build_message, send_message, get_agent_info
from AgentUtil.Logging import config_logger
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.OntoNamespaces import DSO, ECSDI, ACL
from rdflib.namespace import RDF, FOAF

__author__ = 'javier'

logger = config_logger(level=1)

# Configuration stuff
hostname = socket.gethostname()
port = 9021

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteDevoluciones = Agent('AgenteDevoluciones',
                       agn.AgenteDevoluciones,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                         agn.Directorio,
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
    reg_obj = agn[AgenteDevoluciones.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, AgenteDevoluciones.uri))
    gmess.add((reg_obj, FOAF.name, Literal(AgenteDevoluciones.name)))
    gmess.add((reg_obj, DSO.Address, Literal(AgenteDevoluciones.address)))
    gmess.add((reg_obj, DSO.AgentType, agn.AgenteDevoluciones))

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=AgenteDevoluciones.uri,
                      receiver=AgenteDirectorio.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        AgenteDirectorio.address)
    mss_cnt += 1

    return gr


@app.route("/comm")
def comunicacion():
    logger.info("Peticion recibida")
    global mss_cnt
    global dsgraph

    message = request.args['content']
    gm = Graph()
    gm.parse(data=message)

    msgdic = get_message_properties(gm)

    gr = None

    if msgdic is None:
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteDevoluciones.uri, msgcnt=get_count())

    else:
        if msgdic['performative'] != ACL.request:
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteDevoluciones.uri, msgcnt=get_count())

        else:
            content = msgdic['content']
            accion = gm.value(subject=content, predicate=RDF.type)

            if accion == ECSDI.Devolver_producto:
                logger.info("Peticion de retorno")
                if gm.value(subject=accion, predicate=RDF.type) == ECSDI.Devolucion_insatisfaccion and fuera_plazo(gm, content):  # si se ha comprado hace mas de 15 dias, rechazado
                    gr = build_message(Graph(), ACL['refuse'], sender=AgenteDevoluciones.uri, msgcnt=get_count())
                else:
                    comprasbd = open("../data/productos_pedidos.owl")
                    gcomp = Graph()
                    gcomp.parse(comprasbd, format='turtle')
                    compras = gm.subjects(predicate=RDF.type, object=ECSDI.Compra)
                    pesototal = 0.0
                    for compra in compras:
                        productos = gm.objects(subject=compra, predicate=ECSDI.Productos)
                        for prod in productos:
                            gcomp.remove((compra, ECSDI.Productos, prod))
                            peso = gm.value(subject=prod, predicate=ECSDI.Peso)
                            pesototal += peso
                    comprasbd.close()
                    gcomp.serialize(destination='../data/productos_pedidos.owl', format='turtle')

                    gr = Graph()
                    gr.add((content, RDF.type, ECSDI.Devolver_producto))
                    gr.add((content, ECSDI.Peso_total, pesototal))

                    centroLogistico = get_agent_info(agn.AgenteCentroLogistico, AgenteDirectorio, AgenteDevoluciones, get_count())

                    gr = send_message(build_message(gr, perf=ACL.request, sender=AgenteDevoluciones.uri, receiver=centroLogistico.uri, msgcnt=get_count(), content=content), centroLogistico.address)

            else:
                gr = build_message(Graph(), ACL['not-understood'], sender=AgenteDevoluciones.uri, msgcnt=get_count())

    logger.info('Respondemos a la peticion')
    return gr.serialize(format='xml')


def fuera_plazo(gm, content):
    factura = gm.value(subject=content, predicate=ECSDI.Factura)
    fecha = gm.value(subject=factura,predicate=ECSDI.Fecha_entrega).toPython()

    if datetime.date.today() - fecha <= datetime.timedelta(days=15):
        return False
    else:
        return True


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
    register()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


