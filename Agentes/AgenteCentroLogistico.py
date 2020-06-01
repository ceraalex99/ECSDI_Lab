# -*- coding: utf-8 -*-
"""
Created on Fri Dec 27 15:58:13 2013

Esqueleto de agente usando los servicios web de Flask

/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente

Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente

Asume que el agente de registro esta en el puerto 9000

@author: Alex
"""
import sys
import random
from multiprocessing import Process, Queue
import socket
import datetime

from rdflib import Namespace, Graph, Literal
from flask import Flask, request
from AgentUtil.ACLMessages import get_message_properties, build_message, send_message, get_agent_info

from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.OntoNamespaces import DSO, ECSDI, ACL
from rdflib.namespace import RDF, FOAF, XSD

__author__ = 'Alex'


# Configuration stuff

hostname = socket.gethostname()
port = 9012

logger = config_logger(level=1)

agn = Namespace("http://www.agentes.org#")

# Peso del lote
peso_lote = 0.0

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteCentroLogistico = Agent('AgenteCentroLogistico',
                       agn.AgenteCentroLogistico,
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
    reg_obj = agn[AgenteCentroLogistico.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, AgenteCentroLogistico.uri))
    gmess.add((reg_obj, FOAF.name, Literal(AgenteCentroLogistico.name)))
    gmess.add((reg_obj, DSO.Address, Literal(AgenteCentroLogistico.address)))
    gmess.add((reg_obj, DSO.AgentType, agn.AgenteCentroLogistico))

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=AgenteCentroLogistico.uri,
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
    logger.info('Peticion de informacion recibida')

    message = request.args['content']
    gm = Graph()
    gm.parse(data=message)

    msgdic = get_message_properties(gm)

    gr = None

    logger.info('HE LLEGADO AQUI')

    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteCentroLogistico.uri, msgcnt=get_count())
    elif msgdic['performative'] == ACL.request:
        logger.info('HE LLEGADO AQUI2')

        content = msgdic['content']
        accion = gm.value(subject=content, predicate=RDF.type)

        if accion == ECSDI.Pedido:
            for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                gm.remove((item, None, None))

            ofile = open('../data/pedidos_pendientes.owl', "ab")
            ofile.write(gm.serialize(format='turtle'))
            ofile.close()

            peso_pedido = gm.value(subject=content, predicate=ECSDI.Peso)
            logger.info(float(peso_pedido.strip('"')))

            actPesoLote(float(peso_pedido.strip('"')))

            time = datetime.datetime.now().time()
            nine_am = datetime.datetime.strptime("09:00:00", '%H:%M:%S').time()
            nine_pm = datetime.datetime.strptime("21:00:00", '%H:%M:%S').time()
            logger.info('ANTES DE LA HORA')
            if nine_am < time < nine_pm:
                logger.info('HE LLEGADO A LA HORA')
                AgenteTransportista = get_agent_info(agn.AgenteExternoTransportista, AgenteDirectorio,
                                                     AgenteCentroLogistico, get_count())
                g = Graph()
                g.parse('../data/pedidos_pendientes.owl', format='turtle')

                gr = Graph()
                content = ECSDI['Lote_' + str(random.randint(1, sys.float_info.max))]
                gr.add((content, RDF.type, ECSDI.Lote))
                gr.add((content, ECSDI.Peso_lote, Literal(peso_lote, datatype=XSD.float)))

                resposta_precio = send_message(build_message(gr,
                                                             ACL['request'],
                                                             sender=AgenteCentroLogistico.uri,
                                                             receiver=AgenteTransportista.uri,
                                                             msgcnt=get_count(), content=content), AgenteTransportista.address)
                msgdic2 = get_message_properties(resposta_precio)
                content = msgdic2['content']
                precio = resposta_precio.value(subject=content, predicate=ECSDI.Precio_entrega)
                logger.info(precio)
            logger.info('Llego al final')


        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia
            # de registro

            peso = gm.value(subject=content, predicate=ECSDI.Peso)
            prioridad = gm.value(subject=content, predicate=ECSDI.Prioridad)


            msgdic2 = get_message_properties(resposta_precio)
            content = msgdic2['content']

            precio = resposta_precio.value(subject=content, predicate=ECSDI.Precio)

            resposta_proposta = send_message(build_message(informar_transportista(),
                               ACL['inform'],
                               sender=AgenteCentroLogistico.uri,
                               receiver=AgenteTransportista.uri,
                               msgcnt=get_count()), AgenteTransportista.address)
            msgdic3 = get_message_properties(resposta_proposta)
            content = msgdic3['content']

            if msgdic['performative'] == ACL.accept:
                agenteAsistentePersonal = get_agent_info(agn.AgenteExternoAsistentePersonal, AgenteDirectorio, AgenteCentroLogistico, get_count())
                nombre = gm.value(subject=content, predicate=ECSDI.Nombre)
                fecha_llegada = gm.value(subject=content, predicate=ECSDI.Fecha_Final)

                # PIENSA EL TIPO DEL GRAFO
                gr = build_message(informar_usuario(nombre, fecha_llegada, precio),
                        ACL['inform'],
                        sender=AgenteCentroLogistico.uri,
                        receiver=agenteAsistentePersonal.uri,
                        msgcnt=get_count())

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


# DETERMINATE AGENT FUNCTIONS ------------------------------------------------------------------------------

def actPesoLote(peso_pedido):
    global peso_lote
    peso_lote += peso_pedido
    return peso_lote

def enviar_mensaje_transportista(peso, prioridad):
    g = Graph()
    content = ECSDI['Ecsdi_envio']
    g.add((content, RDF.Type, ECSDI.Lote))
    g.add((content, ECSDI.Peso, Literal(peso)))
    g.add((content, ECSDI.Prioridad, Literal(prioridad)))

    return g

def informar_transportista():
    g = Graph()
    content = ECSDI['Ecsdi_envio']
    g.add((content, RDF.Type, ECSDI.Aceptacion_o_denegacion_devolucion))
    g.add((content, ECSDI.Resolucion, Literal('Eres el transportista elegido')))

    return g


def informar_usuario(nombre, fecha_llegada, precio):
    g = Graph()
    content = ECSDI['Ecsdi_envio']
    g.add((content, RDF.Type, ECSDI.Info_transporte))
    g.add((content, ECSDI.Informacion_transportista, Literal(nombre)))
    g.add((content, ECSDI.Fecha_final, Literal(fecha_llegada)))
    g.add((content, ECSDI.Precio, Literal(precio)))

    return g


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    register()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


