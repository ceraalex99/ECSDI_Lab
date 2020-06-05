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
from datetime import datetime, timedelta, date

from rdflib import Namespace, Graph, Literal
from flask import Flask, request
from AgentUtil.ACLMessages import get_message_properties, build_message, send_message, get_agent_info, get_agents_info

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
        gr = Graph()

        logger.info('HE LLEGADO AQUI2')
        global peso_lote

        content = msgdic['content']
        accion = gm.value(subject=content, predicate=RDF.type)

        if accion == ECSDI.Pedido:
            for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                gm.remove((item, None, None))

            ofile = open('../data/pedidos_pendientes.owl', "ab")
            ofile.write(gm.serialize(format='turtle'))
            ofile.close()

            peso_pedido = gm.value(subject=content, predicate=ECSDI.Peso)
            prioridad = gm.value(subject=content, predicate=ECSDI.Prioridad)

            logger.info(prioridad)

            actPesoLote(float(peso_pedido.strip('"')))

            time = datetime.now().time()
            nine_am = datetime.strptime("09:00:00", '%H:%M:%S').time()
            nine_pm = datetime.strptime("23:50:00", '%H:%M:%S').time()
            logger.info('ANTES DE LA HORA')
            if nine_am < time < nine_pm:
                logger.info('HE LLEGADO A LA HORA')
                transportistas = get_agents_info(agn.AgenteExternoTransportista, AgenteDirectorio,
                                                     AgenteCentroLogistico, get_count())
                g = Graph()
                g.parse('../data/pedidos_pendientes.owl', format='turtle')

                ofile = open('../data/pedidos_pendientes.owl', "w")
                ofile.write('')
                ofile.close()



                content = ECSDI['Lote_' + str(random.randint(1, sys.float_info.max))]
                gr.add((content, RDF.type, ECSDI.Lote))
                gr.add((content, ECSDI.Peso_lote, Literal(peso_lote, datatype=XSD.float)))

                oferta_min = [sys.float_info.max, None, None]

                for transportista in transportistas:
                    respuesta_precio = send_message(build_message(gr,
                                                                 ACL['request'],
                                                                 sender=AgenteCentroLogistico.uri,
                                                                 receiver=transportista.uri,
                                                                 msgcnt=get_count(), content=content), transportista.address)
                    subject = respuesta_precio.value(predicate=RDF.type, object=ECSDI.Transportista)
                    precio = respuesta_precio.value(subject=subject, predicate=ECSDI.Precio_entrega)
                    nombre = respuesta_precio.value(subject=subject, predicate=ECSDI.Nombre)
                    if precio.toPython() < oferta_min[0]:
                        oferta_min = [precio.toPython(), transportista, nombre]

                contraoferta = oferta_min[0]*0.95

                content = ECSDI['Contraoferta' + str(random.randint(1, sys.float_info.max))]
                gr.add((content, ECSDI.Contraoferta, Literal(contraoferta, datatype=XSD.float)))
                for transportista in transportistas:
                    respuesta_contraoferta = send_message(build_message(gr,
                                                                 ACL['propose'],
                                                                 sender=AgenteCentroLogistico.uri,
                                                                 receiver=transportista.uri,
                                                                 msgcnt=get_count(), content=content), transportista.address)

                    msgdicres = get_message_properties(respuesta_contraoferta)
                    if msgdicres['performative'] == ACL['accept-proposal']:
                        subject = respuesta_contraoferta.value(predicate=RDF.type, object=ECSDI.Transportista)
                        nombre = respuesta_contraoferta.value(subject=subject, predicate=ECSDI.Nombre)
                        oferta_min = [contraoferta, transportista, nombre]
                        break
                    elif msgdicres['performative'] == ACL.propose:
                        subject = respuesta_contraoferta.value(predicate=RDF.type, object=ECSDI.Transportista)
                        precio = respuesta_contraoferta.value(subject=subject, predicate=ECSDI.Precio_entrega)
                        nombre = respuesta_contraoferta.value(subject=subject, predicate=ECSDI.Nombre)
                        if precio.toPython() < oferta_min[0]:
                            oferta_min = [precio.toPython(), transportista, nombre]

                if prioridad == "true":
                    fecha_llegada = date.today() + timedelta(days=2)
                    oferta_min[0] = oferta_min[0]*2
                else:
                    fecha_llegada = date.today() + timedelta(days=5)
                logger.info(oferta_min[0])
                logger.info(fecha_llegada)

                resposta_proposta = send_message(build_message(informar_transportista(),
                                                               ACL['inform'],
                                                               sender=AgenteCentroLogistico.uri,
                                                               receiver=oferta_min[1].uri,
                                                               msgcnt=get_count()), oferta_min[1].address)
                msgdic2 = get_message_properties(resposta_proposta)

                if msgdic2['performative'] == ACL.agree:
                    logger.info('Acepta')
                    # PIENSA EL TIPO DEL GRAFO
                    gr = build_message(informar_usuario(oferta_min[2], fecha_llegada, oferta_min[0]),
                                       ACL['inform'],
                                       sender=AgenteCentroLogistico.uri,
                                       msgcnt=get_count())

            logger.info('Llego al final')

            peso_lote = 0

        elif accion == ECSDI.Devolver_producto:

            AgentesTransportista = get_agents_info(agn.AgenteExternoTransportista, AgenteDirectorio,
                                                 AgenteCentroLogistico, get_count())

            resp = send_message(build_message(gm, ACL['request'], sender=AgenteCentroLogistico.uri, receiver=AgentesTransportista[0].uri, msgcnt=get_count(), content=content), AgentesTransportista[0].address)
            subject = resp.value(predicate=RDF.type, object=ECSDI.Transportista)
            nombre = resp.value(subject=subject, predicate=ECSDI.Nombre)
            logger.info(nombre)
            gr = build_message(informar_devolucion(nombre), ACL['inform'], sender=AgenteCentroLogistico.uri, msgcnt=get_count())

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

def informar_transportista():
    g = Graph()
    content = ECSDI['Ecsdi_envio']
    g.add((content, RDF.type, ECSDI.Aceptacion_o_denegacion_devolucion))
    g.add((content, ECSDI.Resolucion, Literal('Eres el transportista elegido')))

    return g


def informar_devolucion(nombre):
    g = Graph()
    content = ECSDI['Ecsdi_envio'+ str(get_count())]
    g.add((content, RDF.type, ECSDI.Info_transporte))
    logger.info('SEGUNDO')
    logger.info(nombre)
    g.add((content, ECSDI.Nombre_transportista, Literal(nombre)))

    return g


def informar_usuario(nombre, fecha_llegada, precio):
    g = Graph()
    content = ECSDI['Ecsdi_envio' + str(get_count())]
    g.add((content, RDF.type, ECSDI.Info_transporte))
    g.add((content, ECSDI.Nombre_transportista, Literal(nombre)))
    g.add((content, ECSDI.Fecha_entrega, Literal(fecha_llegada)))
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


